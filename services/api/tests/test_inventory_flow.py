from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import (
    InventoryBalance,
    InventoryReservation,
    Order,
    OrderItem,
    Shipment,
    StockMovement,
)

client = TestClient(app)


def login() -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartorder.local", "password": "SmartOrder123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_catalog_multi_shop_mapping_inventory_and_fulfillment() -> None:
    headers = login()
    assert client.post("/api/v1/orders/mock/sync?count=10", headers=headers).status_code == 200

    warehouses = client.get("/api/v1/warehouses", headers=headers).json()
    assert len(warehouses) == 1
    products = client.get("/api/v1/products", headers=headers).json()
    assert len(products) == 5
    assert sum(len(product["skus"]) for product in products) == 5
    inventory = client.get("/api/v1/inventory", headers=headers).json()
    assert len(inventory) == 5
    assert all(row["on_hand"] == 10000 for row in inventory)

    records = client.get("/api/v1/orders?page_size=10", headers=headers).json()["records"]
    eligible = [
        record
        for record in records
        if record["items"][0]["internal_sku"]
        and record["print_blockers"] == ["订单尚未审核"]
    ]
    distinct = []
    for record in eligible:
        if not distinct or record["platform"] != distinct[-1]["platform"]:
            distinct.append(record)
    mapping_orders = distinct[:2]
    assert len(mapping_orders) == 2
    sku = next(
        sku
        for product in products
        for sku in product["skus"]
        if sku["sku_code"] == mapping_orders[0]["items"][0]["internal_sku"]
    )
    for record in mapping_orders:
        with SessionLocal() as db:
            item = db.scalar(
                select(OrderItem).where(OrderItem.order_id == record["id"])
            )
            item.internal_sku = None
            db.commit()
        mapping = client.post(
            "/api/v1/products/skus/mappings",
            headers=headers,
            json={
                "sku_id": sku["id"],
                "shop_id": record["shop_id"],
                "platform_sku": record["items"][0]["platform_sku"],
            },
        )
        assert mapping.status_code == 200

    audited = client.post(
        "/api/v1/orders/batch/audit",
        headers=headers,
        json={"order_ids": [record["id"] for record in mapping_orders]},
    )
    assert audited.status_code == 200
    assert audited.json()["updated"] == 2

    with SessionLocal() as db:
        active = db.scalars(
            select(InventoryReservation).where(InventoryReservation.status == "ACTIVE")
        ).all()
        assert len(active) == 2
        reserved = db.scalar(select(func.sum(InventoryBalance.reserved)))
        assert reserved == sum(item.quantity for item in active)
        reserve_movements = db.scalars(
            select(StockMovement).where(StockMovement.movement_type == "RESERVED")
        ).all()
        assert len(reserve_movements) == 2

    shipment_response = client.post(
        f"/api/v1/shipments/prepare?order_id={mapping_orders[0]['id']}", headers=headers
    )
    assert shipment_response.status_code == 200
    shipment = shipment_response.json()
    assert shipment["status"] == "PICKING"
    duplicate = client.post(
        f"/api/v1/shipments/prepare?order_id={mapping_orders[0]['id']}", headers=headers
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == shipment["id"]

    scanned = client.post(
        f"/api/v1/shipments/{shipment['id']}/scan",
        headers=headers,
        json={"scan_type": "ORDER", "barcode": shipment["erp_order_no"]},
    )
    assert scanned.status_code == 200
    for _ in range(shipment["items"][0]["expected_quantity"]):
        item_scan = client.post(
            f"/api/v1/shipments/{shipment['id']}/scan",
            headers=headers,
            json={"scan_type": "SKU", "barcode": shipment["items"][0]["barcode"]},
        )
        assert item_scan.status_code == 200
    verified = client.post(f"/api/v1/shipments/{shipment['id']}/verify", headers=headers)
    assert verified.status_code == 200
    shipped = client.post(f"/api/v1/shipments/{shipment['id']}/ship", headers=headers)
    assert shipped.status_code == 200
    assert shipped.json()["status"] == "SHIPPED"
    duplicate_ship = client.post(f"/api/v1/shipments/{shipment['id']}/ship", headers=headers)
    assert duplicate_ship.status_code == 409

    with SessionLocal() as db:
        movement = db.scalar(
            select(StockMovement).where(
                StockMovement.movement_type == "OUTBOUND",
                StockMovement.order_id == mapping_orders[0]["id"],
            )
        )
        assert movement is not None
        assert movement.quantity < 0
        reservations = db.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == mapping_orders[0]["id"]
            )
        ).all()
        assert all(reservation.status == "CONSUMED" for reservation in reservations)
        order = db.get(Order, mapping_orders[0]["id"])
        assert order.status == "SHIPPED"


def test_cancel_order_releases_inventory_once() -> None:
    headers = login()
    client.post("/api/v1/orders/mock/sync?count=5", headers=headers)
    records = client.get("/api/v1/orders?page_size=5", headers=headers).json()["records"]
    order = next(record for record in records if record["print_blockers"] == ["订单尚未审核"])
    audit = client.post(
        "/api/v1/orders/batch/audit", headers=headers, json={"order_ids": [order["id"]]}
    )
    assert audit.json()["updated"] == 1
    with SessionLocal() as db:
        reservation = db.scalar(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order["id"],
                InventoryReservation.status == "ACTIVE",
            )
        )
        assert reservation is not None
    cancelled = client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    second_cancel = client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers)
    assert second_cancel.status_code == 200
    with SessionLocal() as db:
        reservations = db.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order["id"]
            )
        ).all()
        assert len(reservations) == 1
        assert reservations[0].status == "RELEASED"
        movements = db.scalars(
            select(StockMovement).where(
                StockMovement.movement_type == "RELEASE",
                StockMovement.order_id == order["id"],
            )
        ).all()
        assert len(movements) == 1


def test_insufficient_inventory_is_blocked_without_negative_stock() -> None:
    headers = login()
    client.post("/api/v1/orders/mock/sync?count=5", headers=headers)
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "低库存测试商品", "description": "库存不足回归"},
    ).json()
    sku = client.post(
        "/api/v1/products/skus",
        headers=headers,
        json={
            "product_id": product["id"],
            "sku_code": "SO-STAGE4-LOW-001",
            "barcode": "6970000099991",
            "specification": "低库存",
        },
    ).json()
    warehouse = client.get("/api/v1/warehouses", headers=headers).json()[0]
    inbound = client.post(
        "/api/v1/inventory/inbound",
        headers=headers,
        json={
            "warehouse_id": warehouse["id"],
            "sku_id": sku["id"],
            "quantity": 1,
            "low_stock_threshold": 2,
            "note": "入库测试",
        },
    )
    assert inbound.status_code == 200
    content = (
        "平台,平台订单号,商品名称,SKU,数量,实付金额,收件人,手机号,地址\n"
        "CSV,LOW-STOCK-ORDER-001,低库存测试商品,SO-STAGE4-LOW-001,2,39.90,张三,138****0000,浙江省杭州市测试地址***\n"
    ).encode()
    imported = client.post(
        "/api/v1/orders/import",
        headers=headers,
        files={"file": ("low.csv", BytesIO(content), "text/csv")},
    )
    assert imported.status_code == 200
    records = client.get(
        "/api/v1/orders?keyword=LOW-STOCK-ORDER-001", headers=headers
    ).json()["records"]
    assert len(records) == 1
    blocked = client.post(
        "/api/v1/orders/batch/audit", headers=headers, json={"order_ids": [records[0]["id"]]}
    ).json()
    assert blocked["updated"] == 0
    assert any(
        "库存不足" in reason
        for reasons in blocked["blocked"].values()
        for reason in reasons
    )
    with SessionLocal() as db:
        balance = db.scalar(
            select(InventoryBalance).where(InventoryBalance.sku_id == sku["id"])
        )
        assert balance.on_hand == 1
        assert balance.reserved == 0


def test_1000_mock_orders_are_supported_and_idempotent() -> None:
    headers = login()
    first = client.post("/api/v1/orders/mock/sync?count=1000", headers=headers)
    assert first.status_code == 200
    assert first.json()["created"] == 1000
    second = client.post("/api/v1/orders/mock/sync?count=1000", headers=headers)
    assert second.status_code == 200
    assert second.json()["created"] == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1000
        assert db.scalar(select(func.count()).select_from(Shipment)) == 0
