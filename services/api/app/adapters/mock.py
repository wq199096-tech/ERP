from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .base import PlatformAdapter, UnifiedItem, UnifiedOrder

PLATFORMS = ("DOUYIN", "PINDUODUO", "TAOBAO", "JD")
SHOP_IDS = {
    "DOUYIN": "00000000-0000-0000-0000-000000001001",
    "PINDUODUO": "00000000-0000-0000-0000-000000001002",
    "TAOBAO": "00000000-0000-0000-0000-000000001003",
    "JD": "00000000-0000-0000-0000-000000001004",
}
PRODUCTS = (
    ("SO-CUP-450", "304 不锈钢保温杯", "曜石黑 / 450ml", "6970000010011"),
    ("SO-TOWEL-L", "新疆长绒棉浴巾", "雾霾蓝 / 70×140cm", "6970000010028"),
    ("SO-LAMP-W", "护眼阅读台灯", "暖白 / Type-C", "6970000010035"),
    ("SO-BOX-3", "透明收纳箱三件套", "大中小组合", "6970000010042"),
    ("SO-TEA-12", "原叶冷泡茶 12 包", "蜜桃乌龙", "6970000010059"),
)


class MockPlatformAdapter(PlatformAdapter):
    def fetch_orders(self, count: int = 1000) -> list[UnifiedOrder]:
        base = datetime(2026, 10, 17, 9, 30, tzinfo=UTC)
        result: list[UnifiedOrder] = []
        for index in range(count):
            platform = PLATFORMS[index % len(PLATFORMS)]
            sku, product, spec, barcode = PRODUCTS[index % len(PRODUCTS)]
            quantity = 1 + index % 3
            unit_price = Decimal(str(29 + (index % 13) * 7))
            status = ("PENDING_SHIPMENT", "PENDING_SHIPMENT", "SHIPPED", "CANCELLED")[index % 4]
            after_sale = "REFUNDING" if index % 17 == 0 else "NONE"
            created = base - timedelta(minutes=index * 7)
            result.append(
                UnifiedOrder(
                    platform=platform,
                    shop_id=SHOP_IDS[platform],
                    platform_order_no=f"MOCK-{platform}-{index + 1:08d}",
                    status=status,
                    after_sale_status=after_sale,
                    receiver_name=f"测试客户{index + 1}",
                    receiver_phone_masked=f"138****{index % 10000:04d}",
                    receiver_address_masked=f"浙江省杭州市滨江区测试路***号 {index % 50 + 1} 栋",
                    paid_amount=unit_price * quantity,
                    discount_amount=Decimal(index % 5),
                    paid_at=created + timedelta(minutes=2),
                    created_at=created,
                    remark="易碎品，轻拿轻放" if index % 11 == 0 else "",
                    items=(
                        UnifiedItem(
                            platform_sku=f"{platform}-{sku}",
                            internal_sku=None if index % 19 == 0 else sku,
                            product_name=product,
                            specification=spec,
                            quantity=quantity,
                            unit_price=unit_price,
                            barcode=barcode,
                        ),
                    ),
                )
            )
        return result
