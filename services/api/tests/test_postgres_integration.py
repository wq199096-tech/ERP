import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.main import app
from app.models import (
    InventoryBalance,
    InventoryReservation,
    Order,
    OrderItem,
    Shop,
    StockMovement,
    Tenant,
    User,
)
from app.security import Principal, create_token

POSTGRES_URL = os.getenv("DATABASE_URL", "")
assert POSTGRES_URL.startswith("postgresql+psycopg://"), (
    "PostgreSQL 集成测试必须由 CI 显式提供 postgresql+psycopg 数据库地址"
)


def _login(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartorder.local", "password": "SmartOrder123!"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_postgresql_migrations_login_and_order_sync() -> None:
    client = TestClient(app)
    headers = _login(client)

    synced = client.post("/api/v1/orders/mock/sync?count=1000", headers=headers)
    assert synced.status_code == 200
    assert synced.json()["created"] == 1000
    repeated = client.post("/api/v1/orders/mock/sync?count=1000", headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["created"] == 0

    dashboard = client.get("/api/v1/dashboard/summary", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["orders_total"] == 1000

    with SessionLocal() as db:
        assert db.query(Order).count() == 1000


def test_postgresql_multi_shop_shared_internal_sku() -> None:
    client = TestClient(app)
    headers = _login(client)
    synced = client.post("/api/v1/orders/mock/sync?count=10", headers=headers)
    assert synced.status_code == 200

    products = client.get("/api/v1/products", headers=headers).json()
    shared_sku = next(
        sku for product in products for sku in product["skus"] if sku["sku_code"] == "SO-CUP-450"
    )
    records = client.get("/api/v1/orders?page_size=20", headers=headers).json()["records"]
    selected: list[dict] = []
    for record in records:
        if record["audit_status"] == "PENDING" and record["print_blockers"] == [
            "订单尚未审核"
        ] and all(item["shop_id"] != record["shop_id"] for item in selected):
            selected.append(record)
        if len(selected) == 2:
            break
    assert len(selected) == 2

    for record in selected:
        with SessionLocal() as db:
            item = db.query(OrderItem).filter(OrderItem.order_id == record["id"]).one()
            platform_sku = item.platform_sku
            item.internal_sku = None
            db.commit()
        mapping = client.post(
            "/api/v1/products/skus/mappings",
            headers=headers,
            json={
                "sku_id": shared_sku["id"],
                "shop_id": record["shop_id"],
                "platform_sku": platform_sku,
            },
        )
        assert mapping.status_code == 200

    audited = client.post(
        "/api/v1/orders/batch/audit",
        headers=headers,
        json={"order_ids": [record["id"] for record in selected]},
    )
    assert audited.status_code == 200
    assert audited.json()["updated"] == 2
    with SessionLocal() as db:
        reservations = db.query(InventoryReservation).all()
        assert len(reservations) == 2
        assert {reservation.sku_id for reservation in reservations} == {shared_sku["id"]}


def test_postgresql_order_uniqueness_transaction_rollback_and_tenant_isolation() -> None:
    client = TestClient(app)
    headers = _login(client)
    synced = client.post("/api/v1/orders/mock/sync?count=10", headers=headers)
    assert synced.status_code == 200

    with SessionLocal() as db:
        first_order = db.query(Order).order_by(Order.created_at.asc()).first()
        assert first_order is not None

        duplicate = Order(
            tenant_id=first_order.tenant_id,
            shop_id=first_order.shop_id,
            platform=first_order.platform,
            platform_order_no=first_order.platform_order_no,
            erp_order_no=f"{first_order.erp_order_no}-COPY",
            status=first_order.status,
            warehouse_name=first_order.warehouse_name,
            package_id=f"{first_order.package_id}-COPY",
            receiver_name=first_order.receiver_name,
            receiver_phone_masked=first_order.receiver_phone_masked,
            receiver_address_masked=first_order.receiver_address_masked,
            paid_amount=first_order.paid_amount,
        )
        db.add(duplicate)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            pass
        else:
            raise AssertionError("同租户同平台同订单号必须被唯一约束拦截")

        rolled_back = Order(
            tenant_id=first_order.tenant_id,
            shop_id=first_order.shop_id,
            platform=first_order.platform,
            platform_order_no=f"{first_order.platform_order_no}-ROLLBACK",
            erp_order_no=f"{first_order.erp_order_no}-ROLLBACK",
            status=first_order.status,
            warehouse_name=first_order.warehouse_name,
            package_id=f"{first_order.package_id}-ROLLBACK",
            receiver_name=first_order.receiver_name,
            receiver_phone_masked=first_order.receiver_phone_masked,
            receiver_address_masked=first_order.receiver_address_masked,
        )
        db.add(rolled_back)
        db.flush()
        assert db.query(Order).count() == 11
        db.rollback()
        assert db.query(Order).count() == 10

        other_tenant_id = "00000000-0000-0000-0000-000000000002"
        other_user_id = "00000000-0000-0000-0000-000000000202"
        other_shop_id = "00000000-0000-0000-0000-000000001005"
        db.add(Tenant(id=other_tenant_id, name="隔离验证企业"))
        db.flush()
        db.add(
            User(
                id=other_user_id,
                tenant_id=other_tenant_id,
                email="other@smartorder.local",
                password_hash="not-used",
                display_name="隔离用户",
                role="admin",
            )
        )
        db.flush()
        db.add(
            Shop(
                id=other_shop_id,
                tenant_id=other_tenant_id,
                platform="DOUYIN",
                external_id="MOCK-ISOLATED",
                name="隔离店铺",
            )
        )
        db.flush()
        db.add(
            Order(
                tenant_id=other_tenant_id,
                shop_id=other_shop_id,
                platform="DOUYIN",
                platform_order_no="MOCK-ISOLATED-0001",
                erp_order_no="SO-TENANT-ISOLATED-0001",
                status="PENDING_SHIPMENT",
                warehouse_name="隔离仓库",
                package_id="PKG-ISOLATED-0001",
                receiver_name="隔离客户",
                receiver_phone_masked="139****0000",
                receiver_address_masked="上海市浦东新区隔离测试地址***",
                paid_amount=first_order.paid_amount,
            )
        )
        db.commit()

        isolated_headers = {
            "Authorization": f"Bearer {create_token(
                Principal(
                    user_id=other_user_id,
                    tenant_id=other_tenant_id,
                    email="other@smartorder.local",
                    role="admin",
                )
            )}"
        }
        other_orders = client.get("/api/v1/orders", headers=isolated_headers)
        assert other_orders.status_code == 200
        assert other_orders.json()["total"] == 1
        assert other_orders.json()["records"][0]["erp_order_no"] == "SO-TENANT-ISOLATED-0001"
        tenant_orders = client.get("/api/v1/orders", headers=headers)
        assert tenant_orders.json()["total"] == 10
        assert all(
            record["erp_order_no"] != "SO-TENANT-ISOLATED-0001"
            for record in tenant_orders.json()["records"]
        )


def test_postgresql_concurrent_reservation_scan_and_outbound() -> None:
    client = TestClient(app)
    headers = _login(client)
    synced = client.post("/api/v1/orders/mock/sync?count=10", headers=headers)
    assert synced.status_code == 200

    products = client.get("/api/v1/products", headers=headers).json()
    target_sku = next(
        sku
        for product in products
        for sku in product["skus"]
        if sku["sku_code"] == "SO-CUP-450"
    )
    warehouse = client.get("/api/v1/warehouses", headers=headers).json()[0]
    stocktake = client.post(
        "/api/v1/inventory/stocktake",
        headers=headers,
        json={
            "warehouse_id": warehouse["id"],
            "sku_id": target_sku["id"],
            "counted_quantity": 1,
            "note": "并发预留验收",
        },
    )
    assert stocktake.status_code == 200

    with SessionLocal() as db:
        prepared_orders = (
            db.query(Order)
            .filter(Order.audit_status == "PENDING", Order.status == "PENDING_SHIPMENT")
            .order_by(Order.created_at.asc())
            .limit(2)
            .all()
        )
        assert len(prepared_orders) == 2
        for order in prepared_orders:
            order.items[0].internal_sku = "SO-CUP-450"
            order.items[0].barcode = target_sku["barcode"]
            order.items[0].quantity = 1
        db.commit()

    records = client.get("/api/v1/orders?page_size=100", headers=headers).json()["records"]
    candidates = [
        record
        for record in records
        if record["items"][0]["internal_sku"] == "SO-CUP-450"
    ][:2]
    assert len(candidates) == 2
    with SessionLocal() as db:
        for candidate in candidates:
            order = db.get(Order, candidate["id"])
            order.status = "PENDING_SHIPMENT"
            order.after_sale_status = "NONE"
            order.audit_status = "PENDING"
            order.items[0].quantity = 1
        db.commit()

    def audit(order_id: str) -> dict:
        return client.post(
            "/api/v1/orders/batch/audit", headers=headers, json={"order_ids": [order_id]}
        ).json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(audit, [candidate["id"] for candidate in candidates]))
    assert sum(result["updated"] for result in results) == 1
    assert any(
        any("库存不足" in reason for reason in reasons)
        for result in results
        for reasons in result["blocked"].values()
    )
    reserved_order_id = next(
        candidate["id"]
        for candidate, result in zip(candidates, results, strict=True)
        if result["updated"] == 1
    )
    shipment = client.post(
        f"/api/v1/shipments/prepare?order_id={reserved_order_id}", headers=headers
    ).json()
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/scan",
        headers=headers,
        json={"scan_type": "ORDER", "barcode": shipment["erp_order_no"]},
    ).status_code == 200
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/scan",
        headers=headers,
        json={"scan_type": "SKU", "barcode": shipment["items"][0]["barcode"]},
    ).status_code == 200
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/verify", headers=headers
    ).status_code == 200
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/ship", headers=headers
    ).status_code == 200
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/ship", headers=headers
    ).status_code == 409


def test_postgresql_inventory_fulfillment_flow_and_movement_consistency() -> None:
    client = TestClient(app)
    headers = _login(client)
    synced = client.post("/api/v1/orders/mock/sync?count=10", headers=headers)
    assert synced.status_code == 200

    product = client.post(
        "/api/v1/products", headers=headers, json={"name": "PG 一致性商品"}
    )
    assert product.status_code == 200
    product_id = product.json()["id"]
    sku = client.post(
        "/api/v1/products/skus",
        headers=headers,
        json={
            "product_id": product_id,
            "sku_code": "PG-FLOW-SKU-001",
            "barcode": "6970000050001",
            "specification": "PG 一致性规格",
            "purchase_price": "10.00",
            "sale_price": "25.00",
        },
    )
    assert sku.status_code == 200
    sku_id = sku.json()["id"]

    warehouses = client.get("/api/v1/warehouses", headers=headers).json()
    source = warehouses[0]
    target = client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": "WH-PG-FLOW-02", "name": "PG 一致性目标仓", "is_default": False},
    )
    assert target.status_code == 200
    target_id = target.json()["id"]

    inbound = client.post(
        "/api/v1/inventory/inbound",
        headers=headers,
        json={
            "warehouse_id": source["id"],
            "sku_id": sku_id,
            "quantity": 100,
            "note": "PG-FLOW-IN",
        },
    )
    assert inbound.status_code == 200
    transfer = client.post(
        "/api/v1/inventory/transfer",
        headers=headers,
        json={
            "source_warehouse_id": source["id"],
            "target_warehouse_id": target_id,
            "sku_id": sku_id,
            "quantity": 10,
            "note": "PG-FLOW-TRANSFER",
        },
    )
    assert transfer.status_code == 200
    stocktake = client.post(
        "/api/v1/inventory/stocktake",
        headers=headers,
        json={
            "warehouse_id": source["id"],
            "sku_id": sku_id,
            "counted_quantity": 95,
            "note": "PG-FLOW-STOCKTAKE",
        },
    )
    assert stocktake.status_code == 200

    with SessionLocal() as db:
        candidates = (
            db.query(Order)
            .filter(Order.audit_status == "PENDING", Order.status == "PENDING_SHIPMENT")
            .order_by(Order.created_at.asc())
            .limit(3)
            .all()
        )
        assert len(candidates) == 3
        for order, quantity in zip(candidates, (5, 4, 10000), strict=True):
            order.items[0].internal_sku = "PG-FLOW-SKU-001"
            order.items[0].barcode = "6970000050001"
            order.items[0].quantity = quantity
        db.commit()
        order_ids = [order.id for order in candidates]

    audited = client.post(
        "/api/v1/orders/batch/audit", headers=headers, json={"order_ids": order_ids}
    )
    assert audited.status_code == 200
    assert audited.json()["updated"] == 2
    cancel_order_id, outbound_order_id, shortage_order_id = order_ids
    assert any(
        "库存不足" in reason
        for reasons in audited.json()["blocked"].values()
        for reason in reasons
    )
    assert shortage_order_id in audited.json()["blocked"]

    with SessionLocal() as db:
        source_balance = db.query(InventoryBalance).filter_by(
            warehouse_id=source["id"], sku_id=sku_id
        ).one()
        assert (source_balance.on_hand, source_balance.reserved) == (95, 9)

    cancelled = client.post(f"/api/v1/orders/{cancel_order_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["released"] is True
    with SessionLocal() as db:
        source_balance = db.query(InventoryBalance).filter_by(
            warehouse_id=source["id"], sku_id=sku_id
        ).one()
        assert (source_balance.on_hand, source_balance.reserved) == (95, 4)

    shipment_response = client.post(
        f"/api/v1/shipments/prepare?order_id={outbound_order_id}", headers=headers
    )
    assert shipment_response.status_code == 200
    shipment = shipment_response.json()
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/scan",
        headers=headers,
        json={"scan_type": "ORDER", "barcode": shipment["erp_order_no"]},
    ).status_code == 200
    for _ in range(4):
        assert client.post(
            f"/api/v1/shipments/{shipment['id']}/scan",
            headers=headers,
            json={"scan_type": "SKU", "barcode": "6970000050001"},
        ).status_code == 200
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/verify", headers=headers
    ).status_code == 200
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/ship", headers=headers
    ).status_code == 200
    assert client.post(
        f"/api/v1/shipments/{shipment['id']}/ship", headers=headers
    ).status_code == 409

    with SessionLocal() as db:
        source_balance = db.query(InventoryBalance).filter_by(
            warehouse_id=source["id"], sku_id=sku_id
        ).one()
        target_balance = db.query(InventoryBalance).filter_by(
            warehouse_id=target_id, sku_id=sku_id
        ).one()
        assert (source_balance.on_hand, source_balance.reserved) == (91, 0)
        assert target_balance.on_hand == 10
        outbound_reservation = db.query(InventoryReservation).filter_by(
            order_id=outbound_order_id
        ).one()
        assert outbound_reservation.status == "CONSUMED"

        movements = db.query(StockMovement).filter_by(
            warehouse_id=source["id"], sku_id=sku_id
        ).order_by(StockMovement.created_at.asc()).all()
        assert Counter(
            (movement.movement_type, movement.quantity) for movement in movements
        ) == Counter(
            {
                ("INBOUND", 100),
                ("TRANSFER_OUT", -10),
                ("STOCKTAKE", 5),
                ("RESERVED", 5),
                ("RESERVED", 4),
                ("RELEASE", -5),
                ("OUTBOUND", -4),
            }
        )
        assert {
            movement.movement_type: movement.balance_after
            for movement in movements
            if movement.movement_type != "RESERVED"
        } == {
            "INBOUND": 100,
            "TRANSFER_OUT": 90,
            "STOCKTAKE": 95,
            "RELEASE": 91,
            "OUTBOUND": 91,
        }
        # 批量审核按数据库返回顺序预留：先预留 5 件再预留 4 件，可用量依次为 90、86；
        # 先预留 4 件再预留 5 件则为 91、86。两种顺序都是正确的业务结果，
        # 这里断言预留后的可用量序列，而不是断言数据库行序。
        reserved_available = sorted(
            (
                movement.balance_after
                for movement in movements
                if movement.movement_type == "RESERVED"
            ),
            reverse=True,
        )
        assert reserved_available in ([90, 86], [91, 86])
