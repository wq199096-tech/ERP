from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class UnifiedItem:
    platform_sku: str
    internal_sku: str | None
    product_name: str
    specification: str
    quantity: int
    unit_price: Decimal
    barcode: str


@dataclass(frozen=True)
class UnifiedOrder:
    platform: str
    shop_id: str
    platform_order_no: str
    status: str
    after_sale_status: str
    receiver_name: str
    receiver_phone_masked: str
    receiver_address_masked: str
    paid_amount: Decimal
    discount_amount: Decimal
    paid_at: datetime
    created_at: datetime
    remark: str
    items: tuple[UnifiedItem, ...]


class PlatformAdapter(ABC):
    capability_status = "MOCK_ONLY"

    @abstractmethod
    def fetch_orders(self, count: int) -> list[UnifiedOrder]:
        raise NotImplementedError
