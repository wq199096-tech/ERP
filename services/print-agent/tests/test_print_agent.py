from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import printers as printer_driver
from app.main import app, settings, store
from app.store import PrintStore

client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {settings.print_agent_token}"}


def print_payload(order_no: str = "SO-TEST-001", **changes: object) -> dict:
    payload = {
        "data_source": "SERVER_ORDER",
        "server_task_id": f"task-{order_no}",
        "erp_order_no": order_no,
        "order_version": 1,
        "package_id": f"PKG-{order_no}",
        "receiver_name": "测试收件人",
        "receiver_phone": "138****0000",
        "receiver_address": "浙江省杭州市滨江区测试地址 1 栋",
        "warehouse_name": "杭州一号仓",
        "remark": "核对颜色后装箱",
        "items": [
            {
                "internal_sku": "SO-CUP-450",
                "product_name": "304 不锈钢保温杯",
                "specification": "曜石黑 / 450ml",
                "quantity": 2,
                "barcode": "6970000010011",
            }
        ],
    }
    return payload | changes


@pytest.fixture(autouse=True)
def clean_store():
    with store.connect() as db:
        db.execute("DELETE FROM print_attempts")
        db.execute("DELETE FROM print_jobs")
        db.execute("DELETE FROM agent_state")
    yield


def test_requires_token() -> None:
    assert client.get("/api/v1/printers").status_code == 401
    assert client.get("/api/v1/health").status_code == 401


def test_three_print_types_create_valid_pdf() -> None:
    for index, job_type in enumerate(("WAYBILL", "MANIFEST_A4", "PRODUCT_LABEL")):
        response = client.post(
            "/api/v1/jobs",
            headers=HEADERS,
            json={
                "idempotency_key": f"test-three-types-{index}",
                "job_type": job_type,
                "payload": print_payload(f"SO-{index}"),
            },
        )
        assert response.status_code == 200
        job = response.json()
        assert job["status"] == "ACKNOWLEDGED"
        assert Path(job["output_file"]).read_bytes().startswith(b"%PDF")


def test_waybill_pdf_is_100_by_150_mm() -> None:
    response = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "pdf-size-waybill-001",
            "job_type": "WAYBILL",
            "payload": print_payload("SO-SIZE-001"),
        },
    )
    page = PdfReader(response.json()["output_file"]).pages[0]
    width_mm = float(page.mediabox.width) * 25.4 / 72
    height_mm = float(page.mediabox.height) * 25.4 / 72
    assert width_mm == pytest.approx(100, abs=0.2)
    assert height_mm == pytest.approx(150, abs=0.2)


@pytest.mark.parametrize(
    ("job_type", "expected"),
    [("MANIFEST_A4", (210, 297)), ("MANIFEST_A5", (148, 210)), ("MANIFEST_80", (80, 180))],
)
def test_manifest_paper_sizes(job_type: str, expected: tuple[int, int]) -> None:
    response = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
            json={
                "idempotency_key": f"size-{job_type}",
                "job_type": job_type,
                "payload": print_payload(f"SO-{job_type}"),
            },
    ).json()
    page = PdfReader(response["output_file"]).pages[0]
    size = (float(page.mediabox.width) * 25.4 / 72, float(page.mediabox.height) * 25.4 / 72)
    assert size[0] == pytest.approx(expected[0], abs=0.2)
    assert size[1] == pytest.approx(expected[1], abs=0.2)


def test_waybill_idempotency_reuses_number() -> None:
    payload = {
        "idempotency_key": "same-order-waybill-001",
        "job_type": "WAYBILL",
            "payload": print_payload("SO-REUSE-1"),
    }
    first = client.post("/api/v1/jobs", headers=HEADERS, json=payload).json()
    second = client.post("/api/v1/jobs", headers=HEADERS, json=payload).json()
    assert first["id"] == second["id"]
    assert first["waybill_no"] == second["waybill_no"]
    assert second["deduplicated"] is True
    assert first["waybill_no"].startswith("TEST-")


def test_failed_job_persists_and_retry_keeps_waybill() -> None:
    created = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "retry-waybill-001",
            "job_type": "WAYBILL",
            "simulate_result": "failure",
            "payload": print_payload("SO-FAIL-1"),
        },
    ).json()
    assert created["status"] == "FAILED"
    retried = client.post(f"/api/v1/jobs/{created['id']}/retry", headers=HEADERS).json()
    assert retried["status"] == "ACKNOWLEDGED"
    assert retried["waybill_no"] == created["waybill_no"]
    assert store.get(created["id"])["status"] == "ACKNOWLEDGED"


def test_persists_1000_queued_jobs() -> None:
    for index in range(1000):
        key = f"bulk-persistence-{index:04d}"
        job = store.create(
            idempotency_key=key,
            job_type="PRODUCT_LABEL",
            printer_name="MockPrinter 智单测试打印机",
            payload={"sku": f"SKU-{index:04d}"},
            waybill_no=None,
        )
        store.transition(job["id"], "QUEUED")
    jobs = store.list(1000)
    assert len(jobs) == 1000
    assert all(job["status"] in {"QUEUED", "ACKNOWLEDGED"} for job in jobs)


def test_restart_marks_interrupted_job_unknown(tmp_path: Path) -> None:
    path = tmp_path / "restart.sqlite3"
    first_store = PrintStore(path)
    job = first_store.create(
        idempotency_key="restart-recovery-001",
        job_type="PRODUCT_LABEL",
        printer_name="MockPrinter 智单测试打印机",
        payload={"sku": "SKU-RECOVERY"},
        waybill_no=None,
    )
    first_store.transition(job["id"], "SUBMITTED")
    restarted_store = PrintStore(path)
    assert restarted_store.recover_interrupted() == 1
    assert restarted_store.get(job["id"])["status"] == "UNKNOWN"


def test_pause_and_resume_queue() -> None:
    assert client.post("/api/v1/queue/pause", headers=HEADERS).json()["queue_paused"] is True
    queued = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "paused-job-001",
            "job_type": "PRODUCT_LABEL",
            "payload": print_payload("SO-PAUSED-001"),
        },
    ).json()
    assert queued["status"] == "QUEUED"
    resumed = client.post("/api/v1/queue/resume", headers=HEADERS).json()
    assert resumed["resumed"] == 1
    assert store.get(queued["id"])["status"] == "ACKNOWLEDGED"


def test_custom_label_schema_preview_and_bounds() -> None:
    template = {
        "schema_version": 1,
        "name": "40x30 测试模板",
        "width_mm": 40,
        "height_mm": 30,
        "elements": [
            {"kind": "text", "x_mm": 2, "y_mm": 2, "width_mm": 30, "height_mm": 5},
            {"kind": "barcode", "x_mm": 2, "y_mm": 10, "width_mm": 35, "height_mm": 10},
            {"kind": "qrcode", "x_mm": 28, "y_mm": 20, "width_mm": 8, "height_mm": 8},
        ],
    }
    response = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "custom-label-schema-001",
            "job_type": "PRODUCT_LABEL",
            "label_template": template,
            "payload": print_payload("SO-LABEL-001"),
        },
    )
    assert response.status_code == 200
    page = PdfReader(response.json()["output_file"]).pages[0]
    assert float(page.mediabox.width) * 25.4 / 72 == pytest.approx(40, abs=0.2)
    bad = template | {
        "elements": [{"kind": "text", "x_mm": 39, "y_mm": 1, "width_mm": 10, "height_mm": 5}]
    }
    invalid = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "custom-label-schema-bad",
            "job_type": "PRODUCT_LABEL",
            "label_template": bad,
        },
    )
    assert invalid.status_code == 422


def test_strict_contract_rejects_missing_fields() -> None:
    response = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "strict-contract-missing-001",
            "job_type": "WAYBILL",
            "payload": {"order_no": "SO-INCOMPLETE"},
        },
    )
    assert response.status_code == 422
    assert "打印数据契约校验失败" in response.json()["detail"]


def test_waybill_and_manifest_render_all_items() -> None:
    payload = print_payload(
        "SO-MULTI-001",
        items=[
            {
                "internal_sku": "SKU-CUP-001",
                "product_name": "CUP-A",
                "specification": "BLACK-450ML",
                "quantity": 2,
                "barcode": "6970000010011",
            },
            {
                "internal_sku": "SKU-LAMP-002",
                "product_name": "LAMP-B",
                "specification": "WARM-TYPEC",
                "quantity": 3,
                "barcode": "6970000010035",
            },
        ],
    )
    waybill = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={"idempotency_key": "multi-waybill-001", "job_type": "WAYBILL", "payload": payload},
    ).json()
    manifest = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "multi-manifest-001",
            "job_type": "MANIFEST_A4",
            "payload": payload,
        },
    ).json()
    waybill_text = PdfReader(waybill["output_file"]).pages[0].extract_text()
    manifest_text = PdfReader(manifest["output_file"]).pages[0].extract_text()
    for value in ("SO-MULTI-001", "SKU-CUP-001", "SKU-LAMP-002", "CUP-A", "LAMP-B"):
        assert value in waybill_text
        assert value in manifest_text
    assert "杭州一号仓" in manifest_text
    assert "核对颜色后装箱" in manifest_text


def test_multi_item_default_label_renders_every_item() -> None:
    payload = print_payload(
        "SO-MULTI-LABEL",
        items=[
            {
                "internal_sku": "SKU-CUP-001",
                "product_name": "CUP-A",
                "specification": "BLACK-450ML",
                "quantity": 2,
                "barcode": "6970000010011",
            },
            {
                "internal_sku": "SKU-LAMP-002",
                "product_name": "LAMP-B",
                "specification": "WARM-TYPEC",
                "quantity": 3,
                "barcode": "6970000010035",
            },
        ],
    )
    job = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "multi-label-001",
            "job_type": "PRODUCT_LABEL",
            "payload": payload,
        },
    ).json()
    pages = PdfReader(job["output_file"]).pages
    assert len(pages) == 2
    assert "SKU-CUP-001" in pages[0].extract_text()
    assert "SKU-LAMP-002" in pages[1].extract_text()


def test_unknown_job_requires_manual_resubmit() -> None:
    job = client.post(
        "/api/v1/jobs",
        headers=HEADERS,
        json={
            "idempotency_key": "unknown-manual-001",
            "job_type": "WAYBILL",
            "simulate_result": "unknown",
            "payload": print_payload("SO-UNKNOWN-001"),
        },
    ).json()
    blocked = client.post(f"/api/v1/jobs/{job['id']}/retry", headers=HEADERS)
    assert blocked.status_code == 409
    retried = client.post(
        f"/api/v1/jobs/{job['id']}/retry?allow_unknown_resubmit=true", headers=HEADERS
    ).json()
    assert retried["status"] == "ACKNOWLEDGED"
    assert retried["waybill_no"] == job["waybill_no"]


def test_printer_state_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        printer_driver,
        "_windows_records",
        lambda: [
            {"Name": "Offline Printer", "WorkOffline": True, "PrinterStatus": 7},
            {
                "Name": "No Paper Printer",
                "WorkOffline": False,
                "PrinterStatus": 3,
                "DetectedErrorState": 4,
            },
        ],
    )
    with pytest.raises(RuntimeError, match="离线"):
        printer_driver._check_printer_status("Offline Printer")
    with pytest.raises(RuntimeError, match="缺纸"):
        printer_driver._check_printer_status("No Paper Printer")


def test_non_windows_submission_is_rejected_before_raw_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(printer_driver.platform, "system", lambda: "Linux")
    with pytest.raises(RuntimeError, match="真实打印仅支持 Windows"):
        printer_driver.submit_pdf("Printer", Path("contract.pdf"), "contract")


def test_1000_jobs_restart_recovery_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "bulk-restart.sqlite3"
    first_store = PrintStore(path)
    for index in range(1000):
        job = first_store.create(
            idempotency_key=f"bulk-restart-{index:04d}",
            job_type="PRODUCT_LABEL",
            printer_name="MockPrinter 智单测试打印机",
            payload={"sku": f"SKU-{index:04d}"},
            waybill_no=None,
        )
        first_store.transition(job["id"], "SUBMITTED")
    second_store = PrintStore(path)
    assert second_store.recover_interrupted() == 1000
    assert second_store.recover_interrupted() == 0
    jobs = second_store.list(1000)
    assert len(jobs) == 1000
    assert all(job["status"] == "UNKNOWN" for job in jobs)
