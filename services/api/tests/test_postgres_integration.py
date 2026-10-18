import os

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Order

POSTGRES_URL = os.getenv("DATABASE_URL", "")


pytestmark = pytest.mark.skipif(
    not POSTGRES_URL.startswith("postgresql+psycopg://")
    or not POSTGRES_URL.rstrip("/").endswith("erp_stage33_test"),
    reason="PostgreSQL 集成测试仅在隔离的 erp_stage33_test 数据库中运行",
)


def test_postgresql_schema_login_orders_and_dashboard() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartorder.local", "password": "SmartOrder123!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    synced = client.post("/api/v1/orders/mock/sync?count=25", headers=headers)
    assert synced.status_code == 200
    assert synced.json()["created"] == 25

    dashboard = client.get("/api/v1/dashboard/summary", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["orders_total"] == 25

    with SessionLocal() as db:
        assert db.query(Order).count() == 25
