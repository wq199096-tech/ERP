import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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
    warehouse_id: Mapped[str | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
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


class ProductCategory(Base):
    __tablename__ = "product_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_product_category_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_product_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_categories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    category: Mapped[ProductCategory | None] = relationship(lazy="joined")
    skus: Mapped[list["ProductSku"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )


class ProductSku(Base):
    __tablename__ = "product_skus"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku_code", name="uq_product_sku_code"),
        Index("ix_product_sku_tenant_barcode", "tenant_id", "barcode"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    sku_code: Mapped[str] = mapped_column(String(100))
    barcode: Mapped[str] = mapped_column(String(80), default="")
    specification: Mapped[str] = mapped_column(String(120), default="")
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    sale_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    product: Mapped[Product] = relationship(back_populates="skus")


class ProductSkuMapping(Base):
    __tablename__ = "shop_sku_mappings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "platform", "shop_id", "platform_sku", name="uq_shop_sku_mapping"
        ),
        Index("ix_shop_sku_tenant_sku", "tenant_id", "sku_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    sku_id: Mapped[str] = mapped_column(
        ForeignKey("product_skus.id", ondelete="CASCADE"), index=True
    )
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_sku: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
OrderEvent = _generic("OrderEvent", "order_events")
Waybill = _generic("Waybill", "waybills")
WaybillAccount = _generic("WaybillAccount", "waybill_accounts")
Printer = _generic("Printer", "printers")
PrintTemplate = _generic("PrintTemplate", "print_templates")
PurchaseOrder = _generic("PurchaseOrder", "purchase_orders")
Supplier = _generic("Supplier", "suppliers")
FinanceRecord = _generic("FinanceRecord", "finance_records")
AuditLog = _generic("AuditLog", "audit_logs")
OutboxEvent = _generic("OutboxEvent", "outbox_events")


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_warehouse_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(500), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WarehouseLocation(Base):
    __tablename__ = "warehouse_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_warehouse_location"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[str] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "warehouse_id", "sku_id", name="uq_inventory_balance"),
        CheckConstraint("on_hand >= 0", name="ck_inventory_on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="ck_inventory_reserved_non_negative"),
        CheckConstraint("reserved <= on_hand", name="ck_inventory_reserved_not_over_on_hand"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[str] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    sku_id: Mapped[str] = mapped_column(
        ForeignKey("product_skus.id", ondelete="CASCADE"), index=True
    )
    on_hand: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[int] = mapped_column(default=0)
    low_stock_threshold: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_item_id", name="uq_inventory_reservation_order_item"),
        Index("ix_inventory_tenant_order", "tenant_id", "order_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    order_item_id: Mapped[str] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), index=True
    )
    sku_id: Mapped[str] = mapped_column(
        ForeignKey("product_skus.id", ondelete="RESTRICT"), index=True
    )
    warehouse_id: Mapped[str] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "movement_key", name="uq_stock_movement_key"),
        Index("ix_stock_tenant_warehouse_created", "tenant_id", "warehouse_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[str] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    sku_id: Mapped[str] = mapped_column(
        ForeignKey("product_skus.id", ondelete="RESTRICT"), index=True
    )
    movement_type: Mapped[str] = mapped_column(String(40), index=True)
    quantity: Mapped[int]
    balance_after: Mapped[int]
    reservation_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventory_reservations.id", ondelete="SET NULL"), index=True
    )
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True
    )
    movement_key: Mapped[str] = mapped_column(String(160))
    operator_id: Mapped[str] = mapped_column(String(36))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "shipment_no", name="uq_shipment_no"),
        UniqueConstraint("tenant_id", "order_id", name="uq_shipment_order"),
        CheckConstraint(
            "status IN ('PICKING','VERIFIED','SHIPPED','CANCELLED')",
            name="ck_shipment_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[str] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    shipment_no: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="PICKING", index=True)
    order_barcode: Mapped[str] = mapped_column(String(120), default="")
    order_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(String(36))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_by: Mapped[str | None] = mapped_column(String(36))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    order: Mapped[Order] = relationship(lazy="joined")
    items: Mapped[list["ShipmentItem"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan", lazy="selectin"
    )


class ShipmentItem(Base):
    __tablename__ = "shipment_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_item_id", name="uq_shipment_item_order_item"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), index=True
    )
    order_item_id: Mapped[str] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), index=True
    )
    sku_id: Mapped[str] = mapped_column(
        ForeignKey("product_skus.id", ondelete="RESTRICT"), index=True
    )
    sku_code: Mapped[str] = mapped_column(String(100))
    barcode: Mapped[str] = mapped_column(String(80))
    product_name: Mapped[str] = mapped_column(String(255))
    specification: Mapped[str] = mapped_column(String(120), default="")
    expected_quantity: Mapped[int]
    verified_quantity: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    shipment: Mapped[Shipment] = relationship(back_populates="items")


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
