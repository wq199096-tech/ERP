from passlib.hash import pbkdf2_sha256
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    InventoryBalance,
    Product,
    ProductCategory,
    ProductSku,
    Shop,
    Tenant,
    User,
    Warehouse,
)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000101"
SHOPS = (
    ("00000000-0000-0000-0000-000000001001", "DOUYIN", "抖音旗舰店"),
    ("00000000-0000-0000-0000-000000001002", "PINDUODUO", "拼多多一号店"),
    ("00000000-0000-0000-0000-000000001003", "TAOBAO", "天猫品牌店"),
    ("00000000-0000-0000-0000-000000001004", "JD", "京东自营测试店"),
)

WAREHOUSE = ("00000000-0000-0000-0000-000000000901", "WH-HZ-01", "杭州一号仓")
PRODUCTS = (
    ("SO-CUP-450", "304 不锈钢保温杯", "曜石黑 / 450ml", "6970000010011"),
    ("SO-TOWEL-L", "新疆长绒棉浴巾", "雾霾蓝 / 70×140cm", "6970000010028"),
    ("SO-LAMP-W", "护眼阅读台灯", "暖白 / Type-C", "6970000010035"),
    ("SO-BOX-3", "透明收纳箱三件套", "大中小组合", "6970000010042"),
    ("SO-TEA-12", "原叶冷泡茶 12 包", "蜜桃乌龙", "6970000010059"),
)


def ensure_development_data(db: Session) -> None:
    settings = get_settings()
    if settings.is_production or not settings.enable_demo_data:
        return
    if not db.get(Tenant, TENANT_ID):
        db.add(Tenant(id=TENANT_ID, name="杭州智单演示商贸有限公司"))
    user = db.get(User, USER_ID)
    if not user:
        db.add(
            User(
                id=USER_ID,
                tenant_id=TENANT_ID,
                email="admin@smartorder.local",
                password_hash=pbkdf2_sha256.hash("SmartOrder123!"),
                display_name="演示管理员",
                role="admin",
            )
        )
    elif user.email == "admin@smartorder.local":
        user.role = "admin"
    known = set(db.scalars(select(Shop.id).where(Shop.tenant_id == TENANT_ID)))
    for shop_id, platform, name in SHOPS:
        if shop_id not in known:
            db.add(
                Shop(
                    id=shop_id,
                    tenant_id=TENANT_ID,
                    platform=platform,
                    external_id=f"MOCK-{platform}-001",
                    name=name,
                )
            )
    db.commit()


def ensure_development_inventory(db: Session) -> None:
    settings = get_settings()
    if settings.is_production or not settings.enable_demo_data:
        return
    if not db.get(Warehouse, WAREHOUSE[0]):
        if not db.scalar(select(Warehouse).where(Warehouse.tenant_id == TENANT_ID)):
            db.add(
                Warehouse(
                    id=WAREHOUSE[0],
                    tenant_id=TENANT_ID,
                    code=WAREHOUSE[1],
                    name=WAREHOUSE[2],
                    address="浙江省杭州市演示地址***",
                    is_default=True,
                )
            )
            db.flush()
    category = db.scalar(select(ProductCategory).where(ProductCategory.tenant_id == TENANT_ID))
    if not category:
        category = ProductCategory(tenant_id=TENANT_ID, name="演示商品")
        db.add(category)
        db.flush()
    for sku_code, name, specification, barcode in PRODUCTS:
        product = db.scalar(
            select(Product).where(Product.tenant_id == TENANT_ID, Product.name == name)
        )
        if not product:
            product = Product(tenant_id=TENANT_ID, category_id=category.id, name=name)
            db.add(product)
            db.flush()
        sku = db.scalar(
            select(ProductSku).where(
                ProductSku.tenant_id == TENANT_ID, ProductSku.sku_code == sku_code
            )
        )
        if not sku:
            sku = ProductSku(
                tenant_id=TENANT_ID,
                product_id=product.id,
                sku_code=sku_code,
                barcode=barcode,
                specification=specification,
                purchase_price="15.00",
                sale_price="39.90",
            )
            db.add(sku)
            db.flush()
        balance = db.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == TENANT_ID,
                InventoryBalance.warehouse_id == WAREHOUSE[0],
                InventoryBalance.sku_id == sku.id,
            )
        )
        if not balance:
            db.add(
                InventoryBalance(
                    tenant_id=TENANT_ID,
                    warehouse_id=WAREHOUSE[0],
                    sku_id=sku.id,
                    on_hand=10000,
                    reserved=0,
                    low_stock_threshold=100,
                )
            )
    db.commit()
