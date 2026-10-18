from passlib.hash import pbkdf2_sha256
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Shop, Tenant, User

TENANT_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000101"
SHOPS = (
    ("00000000-0000-0000-0000-000000001001", "DOUYIN", "抖音旗舰店"),
    ("00000000-0000-0000-0000-000000001002", "PINDUODUO", "拼多多一号店"),
    ("00000000-0000-0000-0000-000000001003", "TAOBAO", "天猫品牌店"),
    ("00000000-0000-0000-0000-000000001004", "JD", "京东自营测试店"),
)


def ensure_development_data(db: Session) -> None:
    if not db.get(Tenant, TENANT_ID):
        db.add(Tenant(id=TENANT_ID, name="杭州智单演示商贸有限公司"))
    if not db.get(User, USER_ID):
        db.add(
            User(
                id=USER_ID,
                tenant_id=TENANT_ID,
                email="admin@smartorder.local",
                password_hash=pbkdf2_sha256.hash("SmartOrder123!"),
                display_name="演示管理员",
            )
        )
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
