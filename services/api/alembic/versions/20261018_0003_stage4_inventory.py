"""Stage 4 formal catalog, inventory and fulfillment schema.

Revision ID: 20261018_0003
Revises: 20261018_0002

Stage 1 used JSON placeholder tables.  This migration never drops those rows:
each legacy table is renamed, matching rows are copied into the formal schema,
and rows that cannot be mapped safely are isolated with their original JSON.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "20261018_0003"
down_revision = "20261018_0002"
branch_labels = None
depends_on = None


STAGE4_TABLES = (
    "product_categories",
    "products",
    "product_skus",
    "shop_sku_mappings",
    "warehouses",
    "warehouse_locations",
    "inventory_balances",
    "inventory_reservations",
    "stock_movements",
    "shipments",
    "shipment_items",
)
LEGACY_COLUMNS = {"id", "tenant_id", "data", "created_at"}
ALLOWED_STATUS = {
    "ACTIVE", "INACTIVE", "RELEASED", "CONSUMED",
    "PICKING", "VERIFIED", "SHIPPED", "CANCELLED",
}
ARCHIVE_TABLE = sa.Table(
    "stage4_migration_archive",
    sa.MetaData(),
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("tenant_id", sa.String(36), nullable=False),
    sa.Column("table_name", sa.String(100), nullable=False),
    sa.Column("record_id", sa.String(64), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("reason", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_stage4_archive_table_record", "table_name", "record_id"),
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _schema_kind(table: str) -> str:
    columns = _columns(table)
    if not columns:
        return "missing"
    if columns == LEGACY_COLUMNS:
        return "legacy"
    if table not in Base.metadata.tables:
        return "unknown"
    if columns == {column.name for column in Base.metadata.tables[table].columns}:
        return "formal"
    return "unknown"


def _create_archive_table() -> None:
    if _inspector().has_table("stage4_migration_archive"):
        return
    ARCHIVE_TABLE.create(bind=op.get_bind())


def _archive(bind: sa.Connection, *, tenant_id: str, table_name: str, record_id: object, payload: dict, reason: str) -> None:
    bind.execute(
        ARCHIVE_TABLE.insert().values(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            table_name=table_name,
            record_id=str(record_id)[:64],
            payload=payload,
            reason=reason,
            created_at=datetime.now(UTC),
        )
    )


def _legacy_rows(bind: sa.Connection, table: str) -> list[dict]:
    if not _inspector().has_table(f"stage4_legacy_{table}"):
        return []
    return [
        dict(row)
        for row in bind.execute(
            sa.text(f"SELECT id, tenant_id, data, created_at FROM stage4_legacy_{table}")
        ).mappings()
    ]


def _payload(row: dict) -> dict:
    data = row.get("data")
    if not isinstance(data, dict):
        data = {"_invalid_data": data}
    return {
        "id": str(row.get("id")),
        "tenant_id": str(row.get("tenant_id")),
        "data": data,
        "created_at": str(row.get("created_at")),
    }


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _text(value: object, max_length: int, *, required: bool = True) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    if not result or len(result) > max_length:
        return None
    return result


def _status(value: object, default: str) -> str | None:
    result = _text(value, 30, required=False)
    if result is None:
        return default
    return result.upper() if result.upper() in ALLOWED_STATUS else None


def _decimal(value: object, default: Decimal = Decimal("0")) -> Decimal | None:
    if value is None or value == "":
        return default
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if Decimal("0") <= result <= Decimal("999999999999.99") else None


def _int(value: object, *, minimum: int = 0, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= minimum else None


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _new_id(old_id: object, used: set[str]) -> str:
    result = _text(old_id, 36, required=False)
    if result and result not in used:
        return result
    result = str(uuid.uuid4())
    while result in used:
        result = str(uuid.uuid4())
    return result


def _insert(bind: sa.Connection, table_name: str, values: dict) -> None:
    bind.execute(Base.metadata.tables[table_name].insert().values(**values))


def _exists(bind: sa.Connection, table_name: str, conditions: dict) -> bool:
    table = Base.metadata.tables[table_name]
    return bind.scalar(
        sa.select(sa.func.count()).select_from(table).where(
            *[getattr(table.c, key) == value for key, value in conditions.items()]
        )
    ) > 0


def _validate_row_transfer(table: str, source_count: int, migrated: int, archived: int) -> None:
    if source_count != migrated + archived:
        raise RuntimeError(
            f"Stage 4 迁移数据校验失败：{table} 源 {source_count} 行，映射 {migrated} 行，隔离 {archived} 行"
        )


def _migrate_products(bind: sa.Connection, rows: list[dict]) -> tuple[dict, dict]:
    category_names: dict[tuple[str, str], str] = {}
    product_map: dict[str, str] = {}
    product_names: dict[tuple[str, str], str] = {}
    migrated = archived = 0

    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        name = _text(data.get("name"), 255)
        if not tenant_id or not name:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="products", record_id=row.get("id", ""), payload=_payload(row), reason="缺少有效租户或商品名称")
            archived += 1
            continue

        category_name = _text(data.get("category") or data.get("category_name"), 120, required=False)
        category_id = None
        if category_name:
            key = (tenant_id, category_name)
            category_id = category_names.get(key)
            if not category_id:
                category_id = str(uuid.uuid4())
                _insert(bind, "product_categories", {
                    "id": category_id,
                    "tenant_id": tenant_id,
                    "name": category_name,
                    "status": "ACTIVE",
                    "created_at": _datetime(row.get("created_at")) or datetime.now(UTC),
                })
                category_names[key] = category_id

        status = _status(data.get("status"), "ACTIVE")
        if status is None or _exists(bind, "products", {"tenant_id": tenant_id, "name": name}):
            _archive(bind, tenant_id=tenant_id, table_name="products", record_id=row.get("id", ""), payload=_payload(row), reason="商品状态无法映射或名称重复")
            archived += 1
            continue

        product_id = _new_id(row.get("id"), set(product_map.values()))
        created_at = _datetime(row.get("created_at")) or datetime.now(UTC)
        _insert(bind, "products", {
            "id": product_id,
            "tenant_id": tenant_id,
            "category_id": category_id,
            "name": name,
            "description": _text(data.get("description"), 2000, required=False) or "",
            "status": status,
            "created_at": created_at,
            "updated_at": created_at,
        })
        product_map[str(row.get("id"))] = product_id
        product_names[(tenant_id, name)] = product_id
        migrated += 1

    _validate_row_transfer("products", len(rows), migrated, archived)
    return product_map, product_names


def _migrate_skus(bind: sa.Connection, rows: list[dict], product_map: dict, product_names: dict) -> dict:
    sku_map: dict[str, str] = {}
    migrated = archived = 0
    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        sku_code = _text(data.get("sku_code"), 100)
        product_id = product_map.get(str(data.get("product_id") or ""))
        if not product_id:
            product_name = _text(data.get("product_name") or data.get("product"), 255, required=False)
            product_id = product_names.get((tenant_id or "", product_name or ""))
        purchase_price = _decimal(data.get("purchase_price"))
        sale_price = _decimal(data.get("sale_price"))
        status = _status(data.get("status"), "ACTIVE")
        if not tenant_id or not sku_code or not product_id or purchase_price is None or sale_price is None or status is None:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="product_skus", record_id=row.get("id", ""), payload=_payload(row), reason="SKU 商品、金额或状态无法安全映射")
            archived += 1
            continue
        if _exists(bind, "product_skus", {"tenant_id": tenant_id, "sku_code": sku_code}):
            _archive(bind, tenant_id=tenant_id, table_name="product_skus", record_id=row.get("id", ""), payload=_payload(row), reason="内部 SKU 重复")
            archived += 1
            continue

        sku_id = _new_id(row.get("id"), set(sku_map.values()))
        created_at = _datetime(row.get("created_at")) or datetime.now(UTC)
        _insert(bind, "product_skus", {
            "id": sku_id,
            "tenant_id": tenant_id,
            "product_id": product_id,
            "sku_code": sku_code,
            "barcode": _text(data.get("barcode"), 80, required=False) or "",
            "specification": _text(data.get("specification"), 120, required=False) or "",
            "purchase_price": purchase_price,
            "sale_price": sale_price,
            "status": status,
            "created_at": created_at,
            "updated_at": created_at,
        })
        sku_map[str(row.get("id"))] = sku_id
        migrated += 1
    _validate_row_transfer("product_skus", len(rows), migrated, archived)
    return sku_map


def _migrate_mappings(bind: sa.Connection, rows: list[dict], sku_map: dict) -> None:
    migrated = archived = 0
    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        shop_id = _text(data.get("shop_id"), 36, required=False)
        platform_sku = _text(data.get("platform_sku"), 100)
        sku_id = sku_map.get(str(data.get("sku_id") or ""))
        shop = None
        if tenant_id and shop_id:
            shop = bind.execute(
                sa.text("SELECT platform FROM shops WHERE id = :id AND tenant_id = :tenant"),
                {"id": shop_id, "tenant": tenant_id},
            ).mappings().first()
        if not tenant_id or not sku_id or not shop or not platform_sku:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="shop_sku_mappings", record_id=row.get("id", ""), payload=_payload(row), reason="映射缺少有效 SKU、店铺或平台 SKU")
            archived += 1
            continue
        platform = _text(data.get("platform"), 30, required=False) or shop["platform"]
        if _exists(bind, "shop_sku_mappings", {"tenant_id": tenant_id, "shop_id": shop_id, "platform": platform, "platform_sku": platform_sku}):
            _archive(bind, tenant_id=tenant_id, table_name="shop_sku_mappings", record_id=row.get("id", ""), payload=_payload(row), reason="平台 SKU 映射重复")
            archived += 1
            continue
        _insert(bind, "shop_sku_mappings", {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "sku_id": sku_id,
            "shop_id": shop_id,
            "platform": platform,
            "platform_sku": platform_sku,
            "status": _status(data.get("status"), "ACTIVE"),
            "created_at": _datetime(row.get("created_at")) or datetime.now(UTC),
        })
        migrated += 1
    _validate_row_transfer("shop_sku_mappings", len(rows), migrated, archived)


def _migrate_warehouses(bind: sa.Connection, rows: list[dict]) -> dict:
    warehouse_map: dict[str, str] = {}
    migrated = archived = 0
    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        code = _text(data.get("code"), 50)
        name = _text(data.get("name"), 120)
        status = _status(data.get("status"), "ACTIVE")
        if not tenant_id or not code or not name or status is None:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="warehouses", record_id=row.get("id", ""), payload=_payload(row), reason="仓库编码、名称或状态无效")
            archived += 1
            continue
        if _exists(bind, "warehouses", {"tenant_id": tenant_id, "code": code}):
            _archive(bind, tenant_id=tenant_id, table_name="warehouses", record_id=row.get("id", ""), payload=_payload(row), reason="仓库编码重复")
            archived += 1
            continue
        warehouse_id = _new_id(row.get("id"), set(warehouse_map.values()))
        _insert(bind, "warehouses", {
            "id": warehouse_id,
            "tenant_id": tenant_id,
            "code": code,
            "name": name,
            "address": _text(data.get("address"), 500, required=False) or "",
            "is_default": _bool(data.get("is_default")),
            "status": status,
            "created_at": _datetime(row.get("created_at")) or datetime.now(UTC),
        })
        warehouse_map[str(row.get("id"))] = warehouse_id
        migrated += 1
    _validate_row_transfer("warehouses", len(rows), migrated, archived)
    return warehouse_map


def _migrate_locations(bind: sa.Connection, rows: list[dict], warehouse_map: dict) -> dict:
    location_map: dict[str, str] = {}
    migrated = archived = 0
    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        code = _text(data.get("code"), 80)
        warehouse_id = warehouse_map.get(str(data.get("warehouse_id") or ""))
        if not tenant_id or not code or not warehouse_id or _exists(bind, "warehouse_locations", {"tenant_id": tenant_id, "warehouse_id": warehouse_id, "code": code}):
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="warehouse_locations", record_id=row.get("id", ""), payload=_payload(row), reason="库位编码或仓库引用无效")
            archived += 1
            continue
        location_id = _new_id(row.get("id"), set(location_map.values()))
        _insert(bind, "warehouse_locations", {
            "id": location_id,
            "tenant_id": tenant_id,
            "warehouse_id": warehouse_id,
            "code": code,
            "status": _status(data.get("status"), "ACTIVE"),
            "created_at": _datetime(row.get("created_at")) or datetime.now(UTC),
        })
        location_map[str(row.get("id"))] = location_id
        migrated += 1
    _validate_row_transfer("warehouse_locations", len(rows), migrated, archived)
    return location_map


def _migrate_balances(bind: sa.Connection, rows: list[dict], sku_map: dict, warehouse_map: dict) -> dict:
    balance_map: dict[str, str] = {}
    migrated = archived = 0
    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        warehouse_id = warehouse_map.get(str(data.get("warehouse_id") or ""))
        sku_id = sku_map.get(str(data.get("sku_id") or ""))
        on_hand = _int(data.get("on_hand"), minimum=0)
        reserved = _int(data.get("reserved"), minimum=0, default=0)
        threshold = _int(data.get("low_stock_threshold"), minimum=0, default=0)
        if not tenant_id or not warehouse_id or not sku_id or on_hand is None or reserved is None or threshold is None or reserved > on_hand:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="inventory_balances", record_id=row.get("id", ""), payload=_payload(row), reason="库存余额引用无效或违反非负约束")
            archived += 1
            continue
        if _exists(bind, "inventory_balances", {"tenant_id": tenant_id, "warehouse_id": warehouse_id, "sku_id": sku_id}):
            _archive(bind, tenant_id=tenant_id, table_name="inventory_balances", record_id=row.get("id", ""), payload=_payload(row), reason="库存余额重复")
            archived += 1
            continue
        balance_id = _new_id(row.get("id"), set(balance_map.values()))
        _insert(bind, "inventory_balances", {
            "id": balance_id,
            "tenant_id": tenant_id,
            "warehouse_id": warehouse_id,
            "sku_id": sku_id,
            "on_hand": on_hand,
            "reserved": reserved,
            "low_stock_threshold": threshold,
            "updated_at": _datetime(row.get("created_at")) or datetime.now(UTC),
        })
        balance_map[str(row.get("id"))] = balance_id
        migrated += 1
    _validate_row_transfer("inventory_balances", len(rows), migrated, archived)
    return balance_map


def _migrate_reservations(bind: sa.Connection, rows: list[dict], sku_map: dict, warehouse_map: dict) -> dict:
    reservation_map: dict[str, str] = {}
    migrated = archived = 0
    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        order_id = _text(data.get("order_id"), 36, required=False)
        order_item_id = _text(data.get("order_item_id"), 36, required=False)
        sku_id = sku_map.get(str(data.get("sku_id") or ""))
        warehouse_id = warehouse_map.get(str(data.get("warehouse_id") or ""))
        quantity = _int(data.get("quantity"), minimum=1)
        status = _status(data.get("status"), "ACTIVE")
        valid = bool(order_id and order_item_id and bind.scalar(
            sa.text("SELECT COUNT(*) FROM order_items WHERE id = :item AND order_id = :order"),
            {"item": order_item_id, "order": order_id},
        ))
        if not tenant_id or not valid or not sku_id or not warehouse_id or quantity is None or status is None:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="inventory_reservations", record_id=row.get("id", ""), payload=_payload(row), reason="库存预留订单、状态或数量无法安全映射")
            archived += 1
            continue
        reservation_id = _new_id(row.get("id"), set(reservation_map.values()))
        now = datetime.now(UTC)
        _insert(bind, "inventory_reservations", {
            "id": reservation_id,
            "tenant_id": tenant_id,
            "order_id": order_id,
            "order_item_id": order_item_id,
            "sku_id": sku_id,
            "warehouse_id": warehouse_id,
            "quantity": quantity,
            "status": status,
            "released_at": _datetime(data.get("released_at")),
            "created_at": _datetime(row.get("created_at")) or now,
            "updated_at": now,
        })
        reservation_map[str(row.get("id"))] = reservation_id
        migrated += 1
    _validate_row_transfer("inventory_reservations", len(rows), migrated, archived)
    return reservation_map


def _migrate_movements(bind: sa.Connection, rows: list[dict], sku_map: dict, warehouse_map: dict, reservation_map: dict) -> None:
    migrated = archived = 0
    for row in rows:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        warehouse_id = warehouse_map.get(str(data.get("warehouse_id") or ""))
        sku_id = sku_map.get(str(data.get("sku_id") or ""))
        movement_type = _text(data.get("movement_type"), 40)
        movement_key = _text(data.get("movement_key"), 160)
        operator_id = _text(data.get("operator_id"), 36, required=False)
        order_id = _text(data.get("order_id"), 36, required=False)
        reservation_id = reservation_map.get(str(data.get("reservation_id") or ""))
        quantity = _int(data.get("quantity"), minimum=-10**9, default=None)
        balance_after = _int(data.get("balance_after"), minimum=-10**9, default=None)
        if order_id and not bind.scalar(sa.text("SELECT COUNT(*) FROM orders WHERE id = :id"), {"id": order_id}):
            order_id = None
        if not tenant_id or not warehouse_id or not sku_id or not movement_type or not movement_key or not operator_id or quantity is None or balance_after is None:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="stock_movements", record_id=row.get("id", ""), payload=_payload(row), reason="库存流水引用或关键字段无效")
            archived += 1
            continue
        if _exists(bind, "stock_movements", {"tenant_id": tenant_id, "movement_key": movement_key}):
            _archive(bind, tenant_id=tenant_id, table_name="stock_movements", record_id=row.get("id", ""), payload=_payload(row), reason="库存流水键重复")
            archived += 1
            continue
        _insert(bind, "stock_movements", {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "warehouse_id": warehouse_id,
            "sku_id": sku_id,
            "movement_type": movement_type,
            "quantity": quantity,
            "balance_after": balance_after,
            "reservation_id": reservation_id,
            "order_id": order_id,
            "movement_key": movement_key,
            "operator_id": operator_id,
            "note": _text(data.get("note"), 2000, required=False) or "",
            "created_at": _datetime(row.get("created_at")) or datetime.now(UTC),
        })
        migrated += 1
    _validate_row_transfer("stock_movements", len(rows), migrated, archived)


def _migrate_shipments_and_items(bind: sa.Connection, rows: dict[str, list[dict]], sku_map: dict, warehouse_map: dict) -> dict:
    shipment_map: dict[str, str] = {}
    migrated = {name: 0 for name in rows}
    archived = {name: 0 for name in rows}

    for row in rows["shipments"]:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        order_id = _text(data.get("order_id"), 36, required=False)
        warehouse_id = warehouse_map.get(str(data.get("warehouse_id") or ""))
        shipment_no = _text(data.get("shipment_no"), 60)
        status = _status(data.get("status"), "PICKING")
        valid = bool(order_id and tenant_id and bind.scalar(
            sa.text("SELECT COUNT(*) FROM orders WHERE id = :id AND tenant_id = :tenant"),
            {"id": order_id, "tenant": tenant_id},
        ))
        if not valid or not warehouse_id or not shipment_no or status is None:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="shipments", record_id=row.get("id", ""), payload=_payload(row), reason="出库单订单、仓库或状态无效")
            archived["shipments"] += 1
            continue
        if _exists(bind, "shipments", {"tenant_id": tenant_id, "shipment_no": shipment_no}):
            _archive(bind, tenant_id=tenant_id, table_name="shipments", record_id=row.get("id", ""), payload=_payload(row), reason="出库单号重复")
            archived["shipments"] += 1
            continue
        shipment_id = _new_id(row.get("id"), set(shipment_map.values()))
        created_at = _datetime(row.get("created_at")) or datetime.now(UTC)
        _insert(bind, "shipments", {
            "id": shipment_id,
            "tenant_id": tenant_id,
            "order_id": order_id,
            "warehouse_id": warehouse_id,
            "shipment_no": shipment_no,
            "status": status,
            "order_barcode": _text(data.get("order_barcode"), 120, required=False) or "",
            "order_scanned_at": _datetime(data.get("order_scanned_at")),
            "verified_by": _text(data.get("verified_by"), 36, required=False),
            "verified_at": _datetime(data.get("verified_at")),
            "shipped_by": _text(data.get("shipped_by"), 36, required=False),
            "shipped_at": _datetime(data.get("shipped_at")),
            "created_at": created_at,
            "updated_at": created_at,
        })
        shipment_map[str(row.get("id"))] = shipment_id
        migrated["shipments"] += 1

    for row in rows["shipment_items"]:
        tenant_id = _text(row.get("tenant_id"), 36, required=False)
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        shipment_id = shipment_map.get(str(data.get("shipment_id") or ""))
        sku_id = sku_map.get(str(data.get("sku_id") or ""))
        order_item_id = _text(data.get("order_item_id"), 36, required=False)
        product_name = _text(data.get("product_name"), 255)
        expected_quantity = _int(data.get("expected_quantity"), minimum=1)
        verified_quantity = _int(data.get("verified_quantity"), minimum=0, default=0)
        valid = bool(order_item_id and bind.scalar(sa.text("SELECT COUNT(*) FROM order_items WHERE id = :id"), {"id": order_item_id}))
        if not tenant_id or not shipment_id or not sku_id or not valid or not product_name or expected_quantity is None or verified_quantity is None:
            _archive(bind, tenant_id=tenant_id or "unknown", table_name="shipment_items", record_id=row.get("id", ""), payload=_payload(row), reason="出库明细订单项、SKU 或数量无效")
            archived["shipment_items"] += 1
            continue
        _insert(bind, "shipment_items", {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "shipment_id": shipment_id,
            "order_item_id": order_item_id,
            "sku_id": sku_id,
            "sku_code": _text(data.get("sku_code"), 100) or "",
            "barcode": _text(data.get("barcode"), 80, required=False) or "",
            "product_name": product_name,
            "specification": _text(data.get("specification"), 120, required=False) or "",
            "expected_quantity": expected_quantity,
            "verified_quantity": verified_quantity,
            "created_at": _datetime(row.get("created_at")) or datetime.now(UTC),
        })
        migrated["shipment_items"] += 1

    for table_name in rows:
        _validate_row_transfer(table_name, len(rows[table_name]), migrated[table_name], archived[table_name])
    return shipment_map


def _add_order_warehouse_column() -> None:
    if "warehouse_id" in _columns("orders"):
        return
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("warehouse_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_orders_warehouse_id",
            "warehouses",
            ["warehouse_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_orders_warehouse_id", "orders", ["warehouse_id"])


def _order_warehouse_foreign_key() -> dict | None:
    if not _inspector().has_table("orders") or "warehouse_id" not in _columns("orders"):
        return None
    for foreign_key in _inspector().get_foreign_keys("orders"):
        if (
            foreign_key.get("referred_table") == "warehouses"
            and foreign_key.get("referred_columns") == ["id"]
            and foreign_key.get("constrained_columns") == ["warehouse_id"]
        ):
            return foreign_key
    return None


def upgrade() -> None:
    _create_archive_table()
    kinds = {table: _schema_kind(table) for table in STAGE4_TABLES}
    unknown = {table: kind for table, kind in kinds.items() if kind == "unknown"}
    if unknown:
        raise RuntimeError(f"Stage 4 迁移遇到未知表结构，已阻止升级：{unknown}")
    if any(kind == "legacy" for kind in kinds.values()) and "warehouse_id" in _columns("orders"):
        raise RuntimeError("历史 JSON 表升级前 orders.warehouse_id 仍引用旧仓库表，请先人工核对备份")

    legacy_tables = [table for table, kind in kinds.items() if kind == "legacy"]
    for table in legacy_tables:
        if _inspector().has_table(f"stage4_legacy_{table}"):
            raise RuntimeError(f"{table} 的 legacy 备份已存在，迁移状态不明确")
    for table in legacy_tables:
        op.rename_table(table, f"stage4_legacy_{table}")

    missing_tables = [table for table, kind in kinds.items() if kind != "formal"]
    if missing_tables:
        Base.metadata.create_all(
            bind=op.get_bind(),
            tables=[table for table in Base.metadata.sorted_tables if table.name in missing_tables],
        )

    if not legacy_tables:
        _add_order_warehouse_column()
        return

    bind = op.get_bind()
    legacy = {table: _legacy_rows(bind, table) for table in STAGE4_TABLES}
    product_map, product_names = _migrate_products(bind, legacy["products"])
    sku_map = _migrate_skus(bind, legacy["product_skus"], product_map, product_names)
    _migrate_mappings(bind, legacy["shop_sku_mappings"], sku_map)
    warehouse_map = _migrate_warehouses(bind, legacy["warehouses"])
    _migrate_locations(bind, legacy["warehouse_locations"], warehouse_map)
    _migrate_balances(bind, legacy["inventory_balances"], sku_map, warehouse_map)
    reservation_map = _migrate_reservations(bind, legacy["inventory_reservations"], sku_map, warehouse_map)
    _migrate_movements(bind, legacy["stock_movements"], sku_map, warehouse_map, reservation_map)
    _migrate_shipments_and_items(
        bind,
        {"shipments": legacy["shipments"], "shipment_items": legacy["shipment_items"]},
        sku_map,
        warehouse_map,
    )
    _add_order_warehouse_column()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = _inspector()
    _create_archive_table()
    order_warehouse_fk = _order_warehouse_foreign_key()
    if order_warehouse_fk:
        if "ix_orders_warehouse_id" in {index["name"] for index in inspector.get_indexes("orders")}:
            op.drop_index("ix_orders_warehouse_id", table_name="orders")
        op.drop_constraint(order_warehouse_fk["name"], "orders", type_="foreignkey")
        op.drop_column("orders", "warehouse_id")

    # Retain any records created after upgrade in the audit archive before
    # restoring the pre-upgrade legacy snapshot.
    for table_name in reversed(STAGE4_TABLES):
        if not inspector.has_table(table_name):
            continue
        table = Base.metadata.tables[table_name]
        rows = [dict(row) for row in bind.execute(sa.select(table)).mappings()]
        for row in rows:
            _archive(
                bind,
                tenant_id=str(row.get("tenant_id", "unknown")),
                table_name=table_name,
                record_id=row.get("id", ""),
                payload=_json_safe(row),
                reason="Stage 4 downgrade 前保留正式表数据",
            )

    for table_name in reversed(STAGE4_TABLES):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
        legacy_name = f"stage4_legacy_{table_name}"
        if inspector.has_table(legacy_name):
            op.rename_table(legacy_name, table_name)
