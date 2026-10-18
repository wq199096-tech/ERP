import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(30), default="viewer", index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        UniqueConstraint("tenant_id", "platform", "external_id", name="uq_shop_external"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="MOCK")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "platform", "shop_id", "platform_order_no", name="uq_order_platform"
        ),
        Index("ix_orders_tenant_status_created", "tenant_id", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_order_no: Mapped[str] = mapped_column(String(100))
    erp_order_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    after_sale_status: Mapped[str] = mapped_column(String(30), default="NONE")
    audit_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    print_status: Mapped[str] = mapped_column(String(30), default="NOT_PRINTED")
    version: Mapped[int] = mapped_column(default=1)
    package_id: Mapped[str] = mapped_column(String(80), index=True)
    address_valid: Mapped[bool] = mapped_column(default=True)
    stock_available: Mapped[bool] = mapped_column(default=True)
    receiver_name: Mapped[str] = mapped_column(String(80))
    receiver_phone_masked: Mapped[str] = mapped_column(String(30))
    receiver_address_masked: Mapped[str] = mapped_column(String(500))
    warehouse_name: Mapped[str] = mapped_column(String(120))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    remark: Mapped[str] = mapped_column(Text, default="")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    platform_sku: Mapped[str] = mapped_column(String(100))
    internal_sku: Mapped[str | None] = mapped_column(String(100), index=True)
    product_name: Mapped[str] = mapped_column(String(255))
    specification: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    barcode: Mapped[str] = mapped_column(String(80), default="")
    order: Mapped[Order] = relationship(back_populates="items")


class GenericRecord(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def _generic(name: str, table_name: str) -> type[GenericRecord]:
    return type(name, (GenericRecord,), {"__tablename__": table_name})


Role = _generic("Role", "roles")
Permission = _generic("Permission", "permissions")
ShopConnection = _generic("ShopConnection", "shop_connections")
SyncCursor = _generic("SyncCursor", "sync_cursors")
PlatformEvent = _generic("PlatformEvent", "platform_events")
Product = _generic("Product", "products")
ProductSku = _generic("ProductSku", "product_skus")
ShopSkuMapping = _generic("ShopSkuMapping", "shop_sku_mappings")
OrderEvent = _generic("OrderEvent", "order_events")
Warehouse = _generic("Warehouse", "warehouses")
InventoryBalance = _generic("InventoryBalance", "inventory_balances")
InventoryReservation = _generic("InventoryReservation", "inventory_reservations")
StockMovement = _generic("StockMovement", "stock_movements")
Shipment = _generic("Shipment", "shipments")
ShipmentItem = _generic("ShipmentItem", "shipment_items")
Waybill = _generic("Waybill", "waybills")
WaybillAccount = _generic("WaybillAccount", "waybill_accounts")
Printer = _generic("Printer", "printers")
PrintTemplate = _generic("PrintTemplate", "print_templates")
PurchaseOrder = _generic("PurchaseOrder", "purchase_orders")
Supplier = _generic("Supplier", "suppliers")
FinanceRecord = _generic("FinanceRecord", "finance_records")
AuditLog = _generic("AuditLog", "audit_logs")
OutboxEvent = _generic("OutboxEvent", "outbox_events")


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_print_job_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    erp_order_no: Mapped[str] = mapped_column(String(40), index=True)
    order_version: Mapped[int]
    package_id: Mapped[str] = mapped_column(String(80), index=True)
    operation: Mapped[str] = mapped_column(String(20), default="NORMAL")
    job_type: Mapped[str] = mapped_column(String(40), index=True)
    printer_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), index=True, default="CREATED")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    waybill_no: Mapped[str | None] = mapped_column(String(100))
    system_job_id: Mapped[str | None] = mapped_column(String(100))
    output_file: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PrintAttempt(Base):
    __tablename__ = "print_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    print_job_id: Mapped[str] = mapped_column(
        ForeignKey("print_jobs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrderPrivateData(Base):
    __tablename__ = "order_private_data"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True, index=True
    )
    receiver_name_encrypted: Mapped[str] = mapped_column(Text)
    receiver_phone_encrypted: Mapped[str] = mapped_column(Text)
    receiver_address_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
