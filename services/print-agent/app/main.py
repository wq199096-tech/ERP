import secrets
import uuid
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from .config import get_settings
from .contracts import PrintPayload
from .printers import get_spooler_job_status, list_printers, submit_pdf
from .renderer import render_pdf
from .schemas import LabelTemplate
from .store import FINAL_STATES, RETRYABLE_STATES, PrintStore

settings = get_settings()
settings.output_path.mkdir(parents=True, exist_ok=True)
store = PrintStore(settings.database_path)
recovered_jobs = store.recover_interrupted()
app = FastAPI(title="智单 ERP Print Agent", version="0.1.0")

JobType = Literal["WAYBILL", "MANIFEST_A4", "MANIFEST_A5", "MANIFEST_80", "PRODUCT_LABEL"]


class JobRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=200)
    job_type: JobType
    printer_name: str = "MockPrinter 智单测试打印机"
    payload: dict = Field(default_factory=dict)
    simulate_result: Literal["success", "failure", "unknown"] = "success"
    label_template: LabelTemplate | None = None


class ManualRetryRequest(BaseModel):
    confirmed_waybill_no: str = Field(default="", max_length=100)
    confirmed_spooler_status: str = Field(min_length=1, max_length=50)
    operator_name: str = Field(default="local-operator", min_length=1, max_length=100)
    operator_note: str = Field(min_length=4, max_length=1000)


def authorize(request: Request, authorization: str | None = Header(default=None)) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "Print Agent 仅接受本机请求")
    expected = f"Bearer {settings.print_agent_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "Print Agent 访问令牌无效")


def reconcile_unknown_jobs() -> int:
    """Automatically verify, but never resubmit, jobs that may have reached a spooler."""
    changed = 0
    for job in store.list_by_status("UNKNOWN", limit=1000):
        if not job["system_job_id"] or job["printer_name"].startswith("MockPrinter"):
            continue
        try:
            result = get_spooler_job_status(job["printer_name"], job["system_job_id"])
            message = f"重启后 Spooler 自动核对：{result['message']}"
            new_status = (
                result["status"] if result["status"] in {"PRINTED", "FAILED"} else "UNKNOWN"
            )
        except Exception as exc:
            message = f"重启后 Spooler 核对失败：{exc}"
            new_status = "UNKNOWN"
        current = store.get(job["id"])
        if current and current["status"] != new_status:
            store.transition(job["id"], new_status, message)
            changed += 1
    return changed


reconciled_jobs = reconcile_unknown_jobs()


@app.get("/api/v1/health", dependencies=[Depends(authorize)])
def health() -> dict:
    return {
        "status": "ok",
        "service": "smartorder-print-agent",
        "mode": "MOCK_ENABLED",
        "queue_paused": store.is_queue_paused(),
        "recovered_jobs": recovered_jobs,
        "reconciled_jobs": reconciled_jobs,
    }


@app.get("/api/v1/printers", dependencies=[Depends(authorize)])
def printers() -> list[dict]:
    return list_printers()


@app.get("/api/v1/jobs", dependencies=[Depends(authorize)])
def jobs(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    return store.list(limit)


def _execute(job: dict, simulate_result: str) -> dict:
    if job["status"] in FINAL_STATES:
        return job
    store.transition(job["id"], "QUEUED")
    output = settings.output_path / f"{job['id']}.pdf"
    payload = job["payload"] | ({"waybill_no": job["waybill_no"]} if job["waybill_no"] else {})
    try:
        render_pdf(job["job_type"], payload, output)
    except Exception as exc:
        return store.transition(job["id"], "FAILED", f"PDF 渲染失败：{exc}")
    store.transition(job["id"], "RENDERED", "PDF 已渲染完成", output_file=str(output))
    if not job["printer_name"].startswith("MockPrinter"):
        try:
            spooler_job_id = submit_pdf(job["printer_name"], output, job["id"])
            return store.transition(
                job["id"],
                "SUBMITTED",
                "Windows Spooler 已接收；实际出纸状态需人工或设备回执确认",
                system_job_id=spooler_job_id,
            )
        except RuntimeError as exc:
            return store.transition(job["id"], "FAILED", str(exc))
        except Exception as exc:
            return store.transition(job["id"], "FAILED", f"Windows 打印失败：{exc}")
    if simulate_result == "failure":
        return store.transition(job["id"], "FAILED", "MockPrinter 模拟离线")
    if simulate_result == "unknown":
        return store.transition(job["id"], "UNKNOWN", "系统队列未返回纸张输出确认")
    return store.transition(
        job["id"],
        "ACKNOWLEDGED",
        "MockPrinter 已接收；不等同于真实纸张已输出",
    )


def _spooler_status_for_job(job: dict) -> dict[str, str]:
    if not job["system_job_id"]:
        return {"status": "NO_SPOOLER", "message": "任务尚未获得 Spooler 作业标识"}
    try:
        return get_spooler_job_status(job["printer_name"], job["system_job_id"])
    except Exception as exc:
        return {"status": "UNKNOWN", "message": f"Spooler 状态查询失败：{exc}"}


@app.post("/api/v1/jobs", dependencies=[Depends(authorize)])
def create_job(payload: JobRequest) -> dict:
    existing = store.get_by_key(payload.idempotency_key)
    if existing:
        return existing | {"deduplicated": True}
    try:
        print_payload = PrintPayload.model_validate(payload.payload)
    except ValidationError as exc:
        raise HTTPException(422, f"打印数据契约校验失败：{str(exc)}") from exc
    waybill_no = None
    if payload.job_type == "WAYBILL":
        waybill_no = print_payload.reuse_waybill_no or f"TEST-{uuid.uuid4().hex[:16].upper()}"
    request_payload = print_payload.model_dump()
    if payload.job_type == "PRODUCT_LABEL" and payload.label_template:
        request_payload = request_payload | {"label_template": payload.label_template.model_dump()}
    job = store.create(
        idempotency_key=payload.idempotency_key,
        job_type=payload.job_type,
        printer_name=payload.printer_name,
        payload=request_payload,
        waybill_no=waybill_no,
    )
    if store.is_queue_paused():
        return store.transition(job["id"], "QUEUED", "队列已暂停") | {
            "deduplicated": False,
            "queue_paused": True,
        }
    return _execute(job, payload.simulate_result) | {"deduplicated": False}


@app.post("/api/v1/queue/pause", dependencies=[Depends(authorize)])
def pause_queue() -> dict:
    store.set_queue_paused(True)
    return {"queue_paused": True}


@app.post("/api/v1/queue/resume", dependencies=[Depends(authorize)])
def resume_queue() -> dict:
    store.set_queue_paused(False)
    queued = [job for job in store.list(1000) if job["status"] == "QUEUED"]
    for job in queued:
        _execute(job, "success")
    return {"queue_paused": False, "resumed": len(queued)}


@app.post("/api/v1/jobs/{job_id}/retry", dependencies=[Depends(authorize)])
def retry_job(
    job_id: str,
    simulate_result: str = "success",
    body: ManualRetryRequest | None = None,
) -> dict:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "打印任务不存在")
    if job["status"] not in RETRYABLE_STATES:
        raise HTTPException(409, "仅失败或状态未知的任务允许重试")
    if job["status"] == "UNKNOWN":
        if body is None:
            raise HTTPException(422, "状态未知重试必须提交人工核验结果")
        expected_waybill = job["waybill_no"] or "NO_WAYBILL"
        expected_status = _spooler_status_for_job(job)["status"]
        if not secrets.compare_digest(body.confirmed_waybill_no, expected_waybill):
            raise HTTPException(409, "人工核验的原运单号不一致")
        if not secrets.compare_digest(body.confirmed_spooler_status, expected_status):
            raise HTTPException(409, "人工核验的 Spooler 状态不一致")
        store.record_audit(
            job_id,
            body.operator_name,
            "MANUAL_RETRY_CONFIRMED",
            f"原始运单号和 Spooler 状态已核对；备注：{body.operator_note}",
        )
        job = store.transition(
            job["id"],
            "UNKNOWN",
            "人工核验通过后重新提交；沿用原运单号，不重新取号",
        )
    else:
        store.record_audit(job_id, "local-operator", "FAILED_RETRY", "失败任务重试")
    return _execute(job, simulate_result)


@app.post("/api/v1/jobs/{job_id}/cancel", dependencies=[Depends(authorize)])
def cancel_job(job_id: str) -> dict:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "打印任务不存在")
    if job["status"] in FINAL_STATES:
        raise HTTPException(409, "任务已经结束，不能取消")
    return store.transition(job_id, "CANCELLED", "用户取消")


@app.post("/api/v1/jobs/{job_id}/confirm-printed", dependencies=[Depends(authorize)])
def confirm_printed(job_id: str) -> dict:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "打印任务不存在")
    if job["status"] not in {"ACKNOWLEDGED", "UNKNOWN"}:
        raise HTTPException(409, "仅已接收或状态未知的任务可人工确认出纸")
    store.record_audit(job_id, "local-operator", "MANUAL_PRINT_CONFIRMED", "操作员确认纸张已输出")
    return store.transition(job_id, "PRINTED", "操作员人工确认纸张已输出")


@app.get("/api/v1/jobs/{job_id}/verification", dependencies=[Depends(authorize)])
def verification(job_id: str) -> dict:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "打印任务不存在")
    return {
        "job_id": job["id"],
        "job_type": job["job_type"],
        "status": job["status"],
        "printer_name": job["printer_name"],
        "erp_order_no": job["payload"].get("erp_order_no"),
        "package_id": job["payload"].get("package_id"),
        "waybill_no": job["waybill_no"],
        "system_job_id": job["system_job_id"],
        "output_file": job["output_file"],
        "spooler_status": _spooler_status_for_job(job),
        "attempts": store.list_attempts(job_id),
    }


@app.get("/api/v1/jobs/{job_id}/spooler-status", dependencies=[Depends(authorize)])
def spooler_status(job_id: str) -> dict:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "打印任务不存在")
    if not job["system_job_id"]:
        raise HTTPException(409, "任务还没有 Spooler 作业标识")
    return get_spooler_job_status(job["printer_name"], job["system_job_id"])


@app.post("/api/v1/preview/{job_type}", dependencies=[Depends(authorize)])
def preview(job_type: JobType, payload: dict | None = None) -> FileResponse:
    if job_type == "PRODUCT_LABEL" and payload and payload.get("label_template"):
        payload = payload | {
            "label_template": LabelTemplate.model_validate(payload["label_template"]).model_dump()
        }
    output = settings.output_path / f"preview-{job_type.lower()}-{uuid.uuid4().hex[:8]}.pdf"
    render_pdf(job_type, payload or {}, output)
    return FileResponse(output, media_type="application/pdf", filename=output.name)


@app.get("/api/v1/jobs/{job_id}/pdf", dependencies=[Depends(authorize)])
def job_pdf(job_id: str) -> FileResponse:
    job = store.get(job_id)
    if not job or not job["output_file"]:
        raise HTTPException(404, "该任务没有可用的 PDF")
    return FileResponse(job["output_file"], media_type="application/pdf")
