"""Stage 4 formal catalog, inventory and fulfillment schema.

Revision ID: 20261018_0003
Revises: 20261018_0002
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "20261018_0003"
down_revision = "20261018_0002"
branch_labels = None
depends_on = None

STAGE4_TABLES = {
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
}


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    # These were Stage 1 placeholders.  Stage 4 replaces their JSON payloads with
    # relational, constrained stock records.
    # A fresh Stage 4 database may have created the new formal schema during the
    # initial metadata upgrade.  Remove the orders -> warehouses dependency before
    # replacing the placeholder/formal tables; it is restored after recreation.
    order_columns = _columns("orders")
    had_warehouse_column = "warehouse_id" in order_columns
    if had_warehouse_column:
        inspector = sa.inspect(op.get_bind())
        existing_fks = inspector.get_foreign_keys("orders")
        existing_indexes = {index["name"] for index in inspector.get_indexes("orders")}
        if "ix_orders_warehouse_id" in existing_indexes:
            op.drop_index("ix_orders_warehouse_id", table_name="orders")
        with op.batch_alter_table("orders") as batch:
            for foreign_key in existing_fks:
                if not foreign_key.get("name"):
                    continue
                if foreign_key.get("referred_table") == "warehouses" and foreign_key.get(
                    "referred_columns"
                ) == ["id"] and foreign_key.get("constrained_columns") == ["warehouse_id"]:
                    batch.drop_constraint(foreign_key["name"], type_="foreignkey")
            batch.drop_column("warehouse_id")

    for table_name in (
        "shipment_items",
        "shipments",
        "stock_movements",
        "inventory_reservations",
        "inventory_balances",
        "warehouse_locations",
        "warehouses",
        "shop_sku_mappings",
        "product_skus",
        "products",
        "product_categories",
    ):
        if sa.inspect(op.get_bind()).has_table(table_name):
            op.drop_table(table_name)

    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[table for table in Base.metadata.sorted_tables if table.name in STAGE4_TABLES],
    )

    if "warehouse_id" not in _columns("orders"):
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


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("orders"):
        columns = _columns("orders")
        if "warehouse_id" in columns:
            op.drop_index("ix_orders_warehouse_id", table_name="orders")
            op.drop_constraint("fk_orders_warehouse_id", "orders", type_="foreignkey")
            op.drop_column("orders", "warehouse_id")

    for table_name in reversed(sorted(STAGE4_TABLES)):
        if sa.inspect(op.get_bind()).has_table(table_name):
            op.drop_table(table_name)
