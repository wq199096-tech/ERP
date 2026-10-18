from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.security import Principal, create_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


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
    assert response.status_code == 200
    assert response.json()["total"] == 0


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
