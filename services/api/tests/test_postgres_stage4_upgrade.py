import json
import os

from sqlalchemy import create_engine, text

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

DATABASE_URL = os.getenv("DATABASE_URL", "")
assert DATABASE_URL.startswith("postgresql+psycopg://"), (
    "Stage 4 历史数据迁移测试必须连接真实 PostgreSQL"
)


def _alembic_config() -> Config:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = Config(os.path.join(root, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(root, "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def _legacy_table(engine, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(f"""
                CREATE TABLE {name} (
                    id VARCHAR(36) PRIMARY KEY,
                    tenant_id VARCHAR(36) NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
        )


def test_postgresql_stage4_legacy_upgrade_preserves_history() -> None:
    engine = create_engine(DATABASE_URL)
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    assert script.get_revision("20261018_0002")

    command.downgrade(config, "20261018_0002")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE orders DROP COLUMN IF EXISTS warehouse_id"))
        for table in (
            "shipment_items", "shipments", "stock_movements", "inventory_reservations",
            "inventory_balances", "warehouse_locations", "warehouses", "shop_sku_mappings",
            "product_skus", "products", "product_categories",
        ):
            connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

        tenant_id = "11111111-1111-1111-1111-111111111111"
        shop_id = "22222222-2222-2222-2222-222222222222"
        connection.execute(
            text("""
                INSERT INTO tenants (id, name, created_at)
                VALUES (:id, '历史迁移租户', now())
            """),
            {"id": tenant_id},
        )
        connection.execute(
            text("""
                INSERT INTO shops (id, tenant_id, platform, external_id, name, status, created_at)
                VALUES (:id, :tenant, 'DOUYIN', 'LEGACY-SHOP-001', '历史迁移店铺', 'ACTIVE', now())
            """),
            {"id": shop_id, "tenant": tenant_id},
        )

        legacy_tables = (
            "products", "product_skus", "shop_sku_mappings", "warehouses", "inventory_balances"
        )
        for table in legacy_tables:
            _legacy_table(engine, table)

        connection.execute(
            text("""
                INSERT INTO products (id, tenant_id, data, created_at) VALUES
                ('legacy-product-0001', :tenant, :valid, now()),
                ('legacy-product-invalid', :tenant, :invalid, now())
            """),
            {
                "tenant": tenant_id,
                "valid": json.dumps(
                    {
                        "name": "历史迁移保温杯",
                        "category": "历史迁移分类",
                        "description": "Stage 1 JSON 数据",
                        "status": "ACTIVE",
                    },
                    ensure_ascii=False,
                ),
                "invalid": '{"description":"缺少商品名称"}',
            },
        )
        connection.execute(
            text("""
                INSERT INTO product_skus (id, tenant_id, data, created_at) VALUES
                ('legacy-sku-0001', :tenant, :data, now())
            """),
            {
                "tenant": tenant_id,
                "data": json.dumps(
                    {
                        "product_id": "legacy-product-0001",
                        "sku_code": "LEGACY-CUP-450",
                        "barcode": "6970000045001",
                        "specification": "历史规格",
                        "purchase_price": "12.50",
                        "sale_price": "35.00",
                        "status": "ACTIVE",
                    },
                    ensure_ascii=False,
                ),
            },
        )
        connection.execute(
            text("""
                INSERT INTO shop_sku_mappings (id, tenant_id, data, created_at) VALUES
                ('legacy-mapping-0001', :tenant, :data, now())
            """),
            {
                "tenant": tenant_id,
                "data": json.dumps(
                    {
                        "sku_id": "legacy-sku-0001",
                        "shop_id": shop_id,
                        "platform_sku": "PLATFORM-CUP-450",
                        "status": "ACTIVE",
                    },
                    ensure_ascii=False,
                ),
            },
        )
        connection.execute(
            text("""
                INSERT INTO warehouses (id, tenant_id, data, created_at) VALUES
                ('legacy-wh-0001', :tenant, :data, now())
            """),
            {
                "tenant": tenant_id,
                "data": json.dumps(
                    {
                        "code": "WH-LEGACY-01",
                        "name": "历史一号仓",
                        "address": "历史地址",
                        "is_default": True,
                        "status": "ACTIVE",
                    },
                    ensure_ascii=False,
                ),
            },
        )
        connection.execute(
            text("""
                INSERT INTO inventory_balances (id, tenant_id, data, created_at) VALUES
                ('legacy-balance-0001', :tenant, :data, now())
            """),
            {
                "tenant": tenant_id,
                "data": json.dumps(
                    {
                        "warehouse_id": "legacy-wh-0001",
                        "sku_id": "legacy-sku-0001",
                        "on_hand": 12,
                        "reserved": 3,
                        "low_stock_threshold": 4,
                    },
                    ensure_ascii=False,
                ),
            },
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        product = connection.execute(
            text("SELECT name, description, status FROM products WHERE name = '历史迁移保温杯'")
        ).mappings().first()
        assert product and product["status"] == "ACTIVE"
        sku = connection.execute(
            text(
                "SELECT purchase_price, sale_price, barcode "
                "FROM product_skus WHERE sku_code = 'LEGACY-CUP-450'"
            )
        ).mappings().one()
        assert str(sku["purchase_price"]) in {"12.50", "12.5"}
        assert str(sku["sale_price"]) in {"35.00", "35.0"}
        assert sku["barcode"] == "6970000045001"
        mapping = connection.execute(
            text("SELECT COUNT(*) FROM shop_sku_mappings WHERE platform_sku = 'PLATFORM-CUP-450'")
        ).scalar_one()
        warehouse = connection.execute(
            text("SELECT name, is_default FROM warehouses WHERE code = 'WH-LEGACY-01'")
        ).mappings().one()
        balance = connection.execute(
            text("""
                SELECT b.on_hand, b.reserved
                FROM inventory_balances b
                JOIN product_skus s ON s.id = b.sku_id
                WHERE s.sku_code = 'LEGACY-CUP-450'
            """)
        ).mappings().one()
        assert mapping == 1
        assert warehouse["name"] == "历史一号仓" and warehouse["is_default"] is True
        assert balance["on_hand"] == 12 and balance["reserved"] == 3
        assert connection.execute(
            text("SELECT COUNT(*) FROM stage4_legacy_products")
        ).scalar_one() == 2
        invalid_archived = connection.execute(
            text("""
                SELECT COUNT(*) FROM stage4_migration_archive
                WHERE table_name = 'products'
                  AND record_id = 'legacy-product-invalid'
                  AND payload -> 'data' ->> 'description' = '缺少商品名称'
            """)
        ).scalar_one()
        assert invalid_archived >= 1
        columns = connection.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'orders'")
        ).scalars().all()
        assert "warehouse_id" in columns


def test_postgresql_stage4_fresh_formal_upgrade_does_not_drop_tables() -> None:
    engine = create_engine(DATABASE_URL)
    config = _alembic_config()
    command.downgrade(config, "20261018_0002")
    command.upgrade(config, "head")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM products")).scalar_one() >= 0
        columns = connection.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'orders'")
        ).scalars().all()
        assert "warehouse_id" in columns
