from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app, settings, store
from app.store import PrintStore

client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {settings.print_agent_token}"}


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
                "payload": {"order_no": f"SO-{index}", "product_name": "自动化测试商品"},
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
            "payload": {"order_no": "SO-SIZE-001"},
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
        json={"idempotency_key": f"size-{job_type}", "job_type": job_type},
    ).json()
    page = PdfReader(response["output_file"]).pages[0]
    size = (float(page.mediabox.width) * 25.4 / 72, float(page.mediabox.height) * 25.4 / 72)
    assert size[0] == pytest.approx(expected[0], abs=0.2)
    assert size[1] == pytest.approx(expected[1], abs=0.2)


def test_waybill_idempotency_reuses_number() -> None:
    payload = {
        "idempotency_key": "same-order-waybill-001",
        "job_type": "WAYBILL",
        "payload": {"order_no": "SO-REUSE-1"},
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
            "payload": {"order_no": "SO-FAIL-1"},
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
            "payload": {"sku": "SKU-PAUSED"},
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
            "payload": {"product_name": "边界测试商品", "barcode": "6970000010011"},
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
