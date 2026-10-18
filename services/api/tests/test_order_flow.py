from io import BytesIO

from fastapi.testclient import TestClient

from app.bootstrap import TENANT_ID
from app.database import Base, SessionLocal
from app.main import app
from app.models import User
from app.security import Principal, create_token

client = TestClient(app)

def login() -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartorder.local", "password": "SmartOrder123!"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_rejects_wrong_password() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartorder.local", "password": "wrong"},
    )
    assert response.status_code == 401


def test_mock_sync_creates_1000_and_is_idempotent() -> None:
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post("/api/v1/orders/mock/sync?count=1000", headers=headers)
    assert first.status_code == 200
    assert first.json() == {"received": 1000, "created": 1000, "updated": 0}
    second = client.post("/api/v1/orders/mock/sync?count=1000", headers=headers)
    assert second.status_code == 200
    assert second.json() == {"received": 1000, "created": 0, "updated": 1000}
    listed = client.get(
        "/api/v1/orders?page=1&page_size=20&platform=DOUYIN&status=PENDING_SHIPMENT",
        headers=headers,
    ).json()
    assert listed["total"] == 250
    assert len(listed["records"]) == 20
    assert all(order["platform"] == "DOUYIN" for order in listed["records"])


def test_tenant_cannot_see_another_tenants_orders() -> None:
    token = login()
    client.post(
        "/api/v1/orders/mock/sync?count=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    other = create_token(Principal(user_id="other", tenant_id="other", email="other@test"))
    response = client.get("/api/v1/orders", headers={"Authorization": f"Bearer {other}"})
    assert response.status_code == 401


def test_csv_duplicate_import_is_idempotent() -> None:
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    content = (
        "平台,平台订单号,商品名称,SKU,数量,实付金额,收件人,手机号,地址\n"
        "CSV,CSV-ORDER-001,测试商品,SKU-001,2,39.90,张三,138****0000,测试地址***\n"
    ).encode()
    files = {"file": ("orders.csv", BytesIO(content), "text/csv")}
    first = client.post("/api/v1/orders/import", headers=headers, files=files).json()
    files = {"file": ("orders.csv", BytesIO(content), "text/csv")}
    second = client.post("/api/v1/orders/import", headers=headers, files=files).json()
    assert first["created"] == 1
    assert second["created"] == 0
    with SessionLocal() as db:
        assert db.execute(Base.metadata.tables["orders"].select()).fetchall()


def test_print_pipeline_blocks_then_creates_idempotent_real_order_tasks() -> None:
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/orders/mock/sync?count=30", headers=headers)
    records = client.get("/api/v1/orders?page_size=30", headers=headers).json()["records"]
    valid = [record for record in records if record["print_blockers"] == ["订单尚未审核"]][:10]
    assert len(valid) == 10
    order_ids = [record["id"] for record in valid]
    audited = client.post(
        "/api/v1/orders/batch/audit", headers=headers, json={"order_ids": order_ids}
    ).json()
    assert audited["updated"] == 10
    body = {
        "order_ids": order_ids,
        "job_types": ["WAYBILL", "MANIFEST_A4", "PRODUCT_LABEL"],
        "printer_name": "MockPrinter 智单测试打印机",
    }
    first = client.post("/api/v1/orders/print/prepare", headers=headers, json=body)
    assert first.status_code == 200
    assert len(first.json()["tasks"]) == 30
    second = client.post("/api/v1/orders/print/prepare", headers=headers, json=body)
    assert [task["id"] for task in first.json()["tasks"]] == [
        task["id"] for task in second.json()["tasks"]
    ]
    task = first.json()["tasks"][0]
    assert task["payload"]["data_source"] == "SERVER_ORDER"
    assert task["payload"]["erp_order_no"]
    assert task["payload"]["order_version"] >= 1
    assert task["payload"]["package_id"]
    assert task["payload"]["warehouse_name"]
    assert task["payload"]["items"]
    item = task["payload"]["items"][0]
    assert item["internal_sku"]
    assert item["product_name"]
    assert item["quantity"] >= 1
    receipt = client.post(
        f"/api/v1/orders/print/tasks/{task['id']}/receipt",
        headers=headers,
        json={"agent_job_id": "agent-1", "status": "FAILED", "error_message": "模拟失败"},
    )
    assert receipt.json()["order_print_status"] == "FAILED"
    blocked_receipt = client.post(
        f"/api/v1/orders/print/tasks/{task['id']}/receipt",
        headers=headers,
        json={"agent_job_id": "agent-2", "status": "PRINTED"},
    )
    assert blocked_receipt.status_code == 409


def test_viewer_cannot_audit_or_print() -> None:
    login()
    with SessionLocal() as db:
        viewer = User(
            tenant_id=TENANT_ID,
            email="viewer@smartorder.local",
            password_hash="unused",
            display_name="只读用户",
            role="viewer",
        )
        db.add(viewer)
        db.commit()
        token = create_token(
            Principal(user_id=viewer.id, tenant_id=TENANT_ID, email=viewer.email, role="viewer")
        )
    response = client.post(
        "/api/v1/orders/batch/audit",
        headers={"Authorization": f"Bearer {token}"},
        json={"order_ids": ["missing"]},
    )
    assert response.status_code == 403


def test_cancelled_refund_and_unaudited_orders_cannot_bypass_checks() -> None:
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/orders/mock/sync?count=20", headers=headers)
    records = client.get("/api/v1/orders?page_size=20", headers=headers).json()["records"]
    rejected = [
        record
        for record in records
        if record["status"] == "CANCELLED" or record["after_sale_status"] != "NONE"
    ][:2]
    pending = next(record for record in records if record["print_blockers"] == ["订单尚未审核"])
    response = client.post(
        "/api/v1/orders/print/prepare",
        headers=headers,
        json={
            "order_ids": [record["id"] for record in rejected] + [pending["id"]],
            "job_types": ["WAYBILL"],
            "printer_name": "MockPrinter 智单测试打印机",
        },
    ).json()
    assert response["tasks"] == []
    assert len(response["blocked"]) == 3
