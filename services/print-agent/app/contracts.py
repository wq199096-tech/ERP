from typing import Literal

from pydantic import BaseModel, Field


class PrintItem(BaseModel):
    internal_sku: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=255)
    specification: str = Field(default="", max_length=120)
    quantity: int = Field(gt=0, le=1000000)
    barcode: str = Field(default="", max_length=80)


class PrintPayload(BaseModel):
    """Complete print payload for a real server order or an explicit manual test."""

    data_source: Literal["SERVER_ORDER", "MANUAL_TEST"]
    server_task_id: str = Field(min_length=1, max_length=100)
    erp_order_no: str = Field(min_length=1, max_length=80)
    order_version: int = Field(gt=0)
    package_id: str = Field(min_length=1, max_length=120)
    receiver_name: str = Field(min_length=1, max_length=120)
    receiver_phone: str = Field(min_length=1, max_length=60)
    receiver_address: str = Field(min_length=4, max_length=1000)
    warehouse_name: str = Field(min_length=1, max_length=180)
    remark: str = Field(default="", max_length=2000)
    reuse_waybill_no: str | None = Field(default=None, max_length=100)
    items: list[PrintItem] = Field(min_length=1, max_length=500)
