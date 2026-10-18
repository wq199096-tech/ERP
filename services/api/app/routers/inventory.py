from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..inventory import consume_shipment_inventory, resolve_order_item_sku
from ..models import (
    InventoryBalance,
    InventoryReservation,
    Order,
    Product,
    ProductCategory,
    ProductSku,
    ProductSkuMapping,
    Shipment,
    ShipmentItem,
    Shop,
    StockMovement,
    Warehouse,
    WarehouseLocation,
)
from ..security import Principal, require_permission

product_router = APIRouter(prefix="/products", tags=["商品档案"])
warehouse_router = APIRouter(prefix="/warehouses", tags=["仓库管理"])
inventory_router = APIRouter(prefix="/inventory", tags=["库存管理"])
shipment_router = APIRouter(prefix="/shipments", tags=["扫码验货"])


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category_id: str | None = None
    description: str = Field(default="", max_length=2000)
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"


class SkuCreate(BaseModel):
    product_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1, max_length=100)
    barcode: str = Field(default="", max_length=80)
    specification: str = Field(default="", max_length=120)
    purchase_price: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("999999999999.99"))
    sale_price: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("999999999999.99"))
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"


class MappingCreate(BaseModel):
    sku_id: str = Field(min_length=1)
    shop_id: str = Field(min_length=1)
    platform_sku: str = Field(min_length=1, max_length=100)


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=500)
    is_default: bool = False


class LocationCreate(BaseModel):
    warehouse_id: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=80)


class StockOperation(BaseModel):
    warehouse_id: str = Field(min_length=1)
    sku_id: str = Field(min_length=1)
    quantity: int = Field(gt=0, le=1000000)
    low_stock_threshold: int = Field(default=0, ge=0, le=1000000)
    note: str = Field(default="", max_length=1000)


class TransferOperation(BaseModel):
    source_warehouse_id: str = Field(min_length=1)
    target_warehouse_id: str = Field(min_length=1)
    sku_id: str = Field(min_length=1)
    quantity: int = Field(gt=0, le=1000000)
    note: str = Field(default="", max_length=1000)


class StocktakeOperation(BaseModel):
    warehouse_id: str = Field(min_length=1)
    sku_id: str = Field(min_length=1)
    counted_quantity: int = Field(ge=0, le=1000000)
    note: str = Field(default="", max_length=1000)


class ReleaseReservation(BaseModel):
    reservation_id: str = Field(min_length=1)
    note: str = Field(min_length=4, max_length=1000)


class ScanRequest(BaseModel):
    scan_type: Literal["ORDER", "SKU"]
    barcode: str = Field(min_length=1, max_length=160)


def _active_warehouse(db: Session, tenant_id: str, warehouse_id: str) -> Warehouse:
    warehouse = db.scalar(
        select(Warehouse).where(
            Warehouse.tenant_id == tenant_id,
            Warehouse.id == warehouse_id,
            Warehouse.status == "ACTIVE",
        )
    )
    if not warehouse:
        raise HTTPException(404, "仓库不存在或已停用")
    return warehouse


def _active_sku(db: Session, tenant_id: str, sku_id: str) -> ProductSku:
    sku = db.scalar(
        select(ProductSku).where(
            ProductSku.tenant_id == tenant_id,
            ProductSku.id == sku_id,
            ProductSku.status == "ACTIVE",
        )
    )
    if not sku:
        raise HTTPException(404, "SKU 不存在或已停用")
    return sku


def _locked_balance(
    db: Session, tenant_id: str, warehouse_id: str, sku_id: str
) -> InventoryBalance | None:
    return db.scalar(
        select(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.warehouse_id == warehouse_id,
            InventoryBalance.sku_id == sku_id,
        )
        .with_for_update()
    )


def _upsert_locked_balance(
    db: Session, tenant_id: str, warehouse_id: str, sku_id: str, threshold: int = 0
) -> InventoryBalance:
    balance = _locked_balance(db, tenant_id, warehouse_id, sku_id)
    if not balance:
        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            on_hand=0,
            reserved=0,
            low_stock_threshold=threshold,
        )
        db.add(balance)
        db.flush()
    return balance


def _movement(
    db: Session,
    principal: Principal,
    *,
    warehouse_id: str,
    sku_id: str,
    movement_type: str,
    quantity: int,
    balance_after: int,
    note: str,
) -> None:
    db.add(
        StockMovement(
            tenant_id=principal.tenant_id,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            movement_type=movement_type,
            quantity=quantity,
            balance_after=balance_after,
            movement_key=f"MANUAL:{datetime.now(UTC).timestamp()}:{sku_id}:{warehouse_id}",
            operator_id=principal.user_id,
            note=note,
        )
    )


def serialize_sku(sku: ProductSku) -> dict:
    return {
        "id": sku.id,
        "product_id": sku.product_id,
        "product_name": sku.product.name,
        "sku_code": sku.sku_code,
        "barcode": sku.barcode,
        "specification": sku.specification,
        "purchase_price": str(sku.purchase_price),
        "sale_price": str(sku.sale_price),
        "status": sku.status,
    }


@product_router.get("/categories")
def list_categories(
    principal: Principal = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    categories = db.scalars(
        select(ProductCategory)
        .where(ProductCategory.tenant_id == principal.tenant_id)
        .order_by(ProductCategory.name)
    ).all()
    return [
        {"id": item.id, "name": item.name, "status": item.status, "created_at": item.created_at}
        for item in categories
    ]


@product_router.post("/categories")
def create_category(
    payload: CategoryCreate,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    item = ProductCategory(tenant_id=principal.tenant_id, name=payload.name.strip())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "分类名称已存在") from exc
    return {"id": item.id, "name": item.name, "status": item.status}


@product_router.get("")
def list_products(
    keyword: str | None = None,
    principal: Principal = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    conditions = [Product.tenant_id == principal.tenant_id]
    if keyword:
        term = f"%{keyword.strip()}%"
        conditions.append(
            or_(Product.name.ilike(term), Product.skus.any(ProductSku.sku_code.ilike(term)))
        )
    products = db.scalars(
        select(Product)
        .where(*conditions)
        .options(selectinload(Product.skus))
        .order_by(Product.created_at.desc())
        .limit(500)
    ).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "category_id": item.category_id,
            "description": item.description,
            "status": item.status,
            "skus": [serialize_sku(sku) for sku in item.skus],
        }
        for item in products
    ]


@product_router.post("")
def create_product(
    payload: ProductCreate,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.category_id:
        category = db.scalar(
            select(ProductCategory).where(
                ProductCategory.tenant_id == principal.tenant_id,
                ProductCategory.id == payload.category_id,
            )
        )
        if not category:
            raise HTTPException(404, "商品分类不存在")
    item = Product(
        tenant_id=principal.tenant_id,
        category_id=payload.category_id,
        name=payload.name.strip(),
        description=payload.description,
        status=payload.status,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "商品名称已存在") from exc
    return {"id": item.id, "name": item.name, "status": item.status}


@product_router.post("/skus")
def create_sku(
    payload: SkuCreate,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    product = db.scalar(
        select(Product).where(
            Product.tenant_id == principal.tenant_id,
            Product.id == payload.product_id,
            Product.status == "ACTIVE",
        )
    )
    if not product:
        raise HTTPException(404, "商品不存在或已停用")
    sku = ProductSku(
        tenant_id=principal.tenant_id,
        product_id=product.id,
        sku_code=payload.sku_code.strip(),
        barcode=payload.barcode.strip(),
        specification=payload.specification,
        purchase_price=payload.purchase_price,
        sale_price=payload.sale_price,
        status=payload.status,
    )
    db.add(sku)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "内部 SKU 或条码冲突") from exc
    return serialize_sku(sku)


@product_router.post("/skus/mappings")
def create_sku_mapping(
    payload: MappingCreate,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    sku = _active_sku(db, principal.tenant_id, payload.sku_id)
    shop = db.scalar(
        select(Shop).where(Shop.tenant_id == principal.tenant_id, Shop.id == payload.shop_id)
    )
    if not shop:
        raise HTTPException(404, "店铺不存在")
    mapping = ProductSkuMapping(
        tenant_id=principal.tenant_id,
        sku_id=sku.id,
        shop_id=shop.id,
        platform=shop.platform,
        platform_sku=payload.platform_sku.strip(),
    )
    db.add(mapping)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "平台 SKU 映射已存在") from exc
    return {
        "id": mapping.id,
        "sku_id": mapping.sku_id,
        "shop_id": mapping.shop_id,
        "platform_sku": mapping.platform_sku,
        "status": mapping.status,
    }


@warehouse_router.get("")
def list_warehouses(
    principal: Principal = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    warehouses = db.scalars(
        select(Warehouse)
        .where(Warehouse.tenant_id == principal.tenant_id)
        .order_by(Warehouse.code)
    ).all()
    return [
        {
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "address": item.address,
            "is_default": item.is_default,
            "status": item.status,
        }
        for item in warehouses
    ]


@warehouse_router.post("")
def create_warehouse(
    payload: WarehouseCreate,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.is_default:
        for warehouse in db.scalars(
            select(Warehouse).where(
                Warehouse.tenant_id == principal.tenant_id, Warehouse.is_default.is_(True)
            )
        ):
            warehouse.is_default = False
    item = Warehouse(
        tenant_id=principal.tenant_id,
        code=payload.code.strip(),
        name=payload.name.strip(),
        address=payload.address,
        is_default=payload.is_default,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "仓库编码已存在") from exc
    return {"id": item.id, "code": item.code, "name": item.name, "status": item.status}


@warehouse_router.post("/locations")
def create_location(
    payload: LocationCreate,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    warehouse = _active_warehouse(db, principal.tenant_id, payload.warehouse_id)
    item = WarehouseLocation(
        tenant_id=principal.tenant_id, warehouse_id=warehouse.id, code=payload.code.strip()
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "库位编码已存在") from exc
    return {"id": item.id, "warehouse_id": item.warehouse_id, "code": item.code}


@inventory_router.get("")
def list_inventory(
    warehouse_id: str | None = None,
    keyword: str | None = None,
    low_stock: bool = False,
    principal: Principal = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    conditions = [InventoryBalance.tenant_id == principal.tenant_id]
    if warehouse_id:
        conditions.append(InventoryBalance.warehouse_id == warehouse_id)
    if keyword:
        term = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                ProductSku.sku_code.ilike(term),
                ProductSku.barcode.ilike(term),
                Product.name.ilike(term),
            )
        )
    if low_stock:
        conditions.append(
            (InventoryBalance.on_hand - InventoryBalance.reserved)
            <= InventoryBalance.low_stock_threshold
        )
    rows = db.execute(
        select(InventoryBalance, Warehouse, ProductSku, Product)
        .join(Warehouse, Warehouse.id == InventoryBalance.warehouse_id)
        .join(ProductSku, ProductSku.id == InventoryBalance.sku_id)
        .join(Product, Product.id == ProductSku.product_id)
        .where(*conditions)
        .order_by(Warehouse.code, ProductSku.sku_code)
        .limit(1000)
    ).all()
    return [
        {
            "id": balance.id,
            "warehouse_id": warehouse.id,
            "warehouse_code": warehouse.code,
            "warehouse_name": warehouse.name,
            "sku_id": sku.id,
            "sku_code": sku.sku_code,
            "product_name": product.name,
            "barcode": sku.barcode,
            "specification": sku.specification,
            "on_hand": balance.on_hand,
            "reserved": balance.reserved,
            "available": balance.on_hand - balance.reserved,
            "low_stock_threshold": balance.low_stock_threshold,
            "low_stock": (balance.on_hand - balance.reserved) <= balance.low_stock_threshold,
        }
        for balance, warehouse, sku, product in rows
    ]


@inventory_router.post("/inbound")
def inbound(
    payload: StockOperation,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    warehouse = _active_warehouse(db, principal.tenant_id, payload.warehouse_id)
    sku = _active_sku(db, principal.tenant_id, payload.sku_id)
    try:
        balance = _upsert_locked_balance(
            db, principal.tenant_id, warehouse.id, sku.id, payload.low_stock_threshold
        )
        balance.on_hand += payload.quantity
        _movement(
            db,
            principal,
            warehouse_id=warehouse.id,
            sku_id=sku.id,
            movement_type="INBOUND",
            quantity=payload.quantity,
            balance_after=balance.on_hand,
            note=payload.note,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "库存并发冲突，请重试") from exc
    return {"on_hand": balance.on_hand, "reserved": balance.reserved}


@inventory_router.post("/transfer")
def transfer(
    payload: TransferOperation,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.source_warehouse_id == payload.target_warehouse_id:
        raise HTTPException(422, "调拨源仓库和目标仓库不能相同")
    source = _active_warehouse(db, principal.tenant_id, payload.source_warehouse_id)
    target = _active_warehouse(db, principal.tenant_id, payload.target_warehouse_id)
    sku = _active_sku(db, principal.tenant_id, payload.sku_id)
    try:
        source_balance = _locked_balance(db, principal.tenant_id, source.id, sku.id)
        source_available = source_balance.on_hand - source_balance.reserved if source_balance else 0
        if source_available < payload.quantity:
            raise HTTPException(409, "调拨源仓库可用库存不足")
        target_balance = _upsert_locked_balance(db, principal.tenant_id, target.id, sku.id)
        source_balance.on_hand -= payload.quantity
        target_balance.on_hand += payload.quantity
        _movement(
            db, principal, warehouse_id=source.id, sku_id=sku.id, movement_type="TRANSFER_OUT",
            quantity=-payload.quantity, balance_after=source_balance.on_hand, note=payload.note,
        )
        _movement(
            db, principal, warehouse_id=target.id, sku_id=sku.id, movement_type="TRANSFER_IN",
            quantity=payload.quantity, balance_after=target_balance.on_hand, note=payload.note,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "库存并发冲突，请重试") from exc
    return {"source_on_hand": source_balance.on_hand, "target_on_hand": target_balance.on_hand}


@inventory_router.post("/stocktake")
def stocktake(
    payload: StocktakeOperation,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    warehouse = _active_warehouse(db, principal.tenant_id, payload.warehouse_id)
    sku = _active_sku(db, principal.tenant_id, payload.sku_id)
    try:
        balance = _upsert_locked_balance(db, principal.tenant_id, warehouse.id, sku.id)
        if payload.counted_quantity < balance.reserved:
            raise HTTPException(409, "盘点数量不能低于已预留库存")
        difference = payload.counted_quantity - balance.on_hand
        balance.on_hand = payload.counted_quantity
        _movement(
            db, principal, warehouse_id=warehouse.id, sku_id=sku.id, movement_type="STOCKTAKE",
            quantity=difference, balance_after=balance.on_hand, note=payload.note,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "库存并发冲突，请重试") from exc
    return {"on_hand": balance.on_hand, "reserved": balance.reserved}


@inventory_router.get("/movements")
def list_movements(
    warehouse_id: str | None = None,
    movement_type: str | None = None,
    principal: Principal = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    conditions = [StockMovement.tenant_id == principal.tenant_id]
    if warehouse_id:
        conditions.append(StockMovement.warehouse_id == warehouse_id)
    if movement_type:
        conditions.append(StockMovement.movement_type == movement_type)
    movements = db.scalars(
        select(StockMovement)
        .where(*conditions)
        .order_by(StockMovement.created_at.desc())
        .limit(500)
    ).all()
    return [
        {
            "id": item.id,
            "warehouse_id": item.warehouse_id,
            "sku_id": item.sku_id,
            "movement_type": item.movement_type,
            "quantity": item.quantity,
            "balance_after": item.balance_after,
            "order_id": item.order_id,
            "note": item.note,
            "created_at": item.created_at,
        }
        for item in movements
    ]


@inventory_router.post("/reservations/release")
def release_reservation(
    payload: ReleaseReservation,
    principal: Principal = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
) -> dict:
    reservation = db.scalar(
        select(InventoryReservation).where(
            InventoryReservation.tenant_id == principal.tenant_id,
            InventoryReservation.id == payload.reservation_id,
            InventoryReservation.status == "ACTIVE",
        )
    )
    if not reservation:
        raise HTTPException(404, "有效库存预留不存在")
    balance = _locked_balance(
        db, principal.tenant_id, reservation.warehouse_id, reservation.sku_id
    )
    if not balance or balance.reserved < reservation.quantity:
        raise HTTPException(409, "库存预留余额异常")
    balance.reserved -= reservation.quantity
    reservation.status = "RELEASED"
    reservation.released_at = datetime.now(UTC)
    db.add(
        StockMovement(
            tenant_id=principal.tenant_id,
            warehouse_id=reservation.warehouse_id,
            sku_id=reservation.sku_id,
            movement_type="RELEASE",
            quantity=-reservation.quantity,
            balance_after=balance.on_hand - balance.reserved,
            movement_key=f"MANUAL_RELEASE:{reservation.id}",
            operator_id=principal.user_id,
            order_id=reservation.order_id,
            reservation_id=reservation.id,
            note=payload.note,
        )
    )
    db.commit()
    return {"reservation_id": reservation.id, "status": reservation.status}


def serialize_shipment(shipment: Shipment) -> dict:
    return {
        "id": shipment.id,
        "shipment_no": shipment.shipment_no,
        "order_id": shipment.order_id,
        "erp_order_no": shipment.order.erp_order_no,
        "warehouse_id": shipment.warehouse_id,
        "warehouse_name": shipment.order.warehouse_name,
        "status": shipment.status,
        "order_scanned_at": shipment.order_scanned_at,
        "verified_at": shipment.verified_at,
        "shipped_at": shipment.shipped_at,
        "items": [
            {
                "id": item.id,
                "sku_code": item.sku_code,
                "barcode": item.barcode,
                "product_name": item.product_name,
                "specification": item.specification,
                "expected_quantity": item.expected_quantity,
                "verified_quantity": item.verified_quantity,
            }
            for item in shipment.items
        ],
    }


@shipment_router.get("")
def list_shipments(
    status: str | None = None,
    principal: Principal = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    conditions = [Shipment.tenant_id == principal.tenant_id]
    if status:
        conditions.append(Shipment.status == status)
    shipments = db.scalars(
        select(Shipment)
        .where(*conditions)
        .options(selectinload(Shipment.items))
        .order_by(Shipment.created_at.desc())
        .limit(500)
    ).all()
    return [serialize_shipment(item) for item in shipments]


@shipment_router.post("/prepare")
def prepare_shipment(
    order_id: str,
    principal: Principal = Depends(require_permission("fulfillment:verify")),
    db: Session = Depends(get_db),
) -> dict:
    order = db.scalar(
        select(Order)
        .where(Order.tenant_id == principal.tenant_id, Order.id == order_id)
        .options(selectinload(Order.items))
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "PENDING_SHIPMENT" or order.audit_status != "APPROVED":
        raise HTTPException(409, "订单必须是已审核的待发货订单")
    existing = db.scalar(
        select(Shipment).where(
            Shipment.tenant_id == principal.tenant_id, Shipment.order_id == order.id
        )
    )
    if existing:
        return serialize_shipment(existing)
    if not order.warehouse_id:
        raise HTTPException(409, "订单尚未分配出库仓库")
    shipment = Shipment(
        tenant_id=principal.tenant_id,
        order_id=order.id,
        warehouse_id=order.warehouse_id,
        shipment_no=f"SHIP-{order.erp_order_no}",
        order_barcode=order.erp_order_no,
    )
    db.add(shipment)
    db.flush()
    for item in order.items:
        sku = resolve_order_item_sku(db, principal.tenant_id, item)
        if not sku:
            raise HTTPException(422, f"SKU 未映射：{item.platform_sku}")
        db.add(
            ShipmentItem(
                tenant_id=principal.tenant_id,
                shipment_id=shipment.id,
                order_item_id=item.id,
                sku_id=sku.id,
                sku_code=sku.sku_code,
                barcode=sku.barcode,
                product_name=item.product_name,
                specification=item.specification or sku.specification,
                expected_quantity=item.quantity,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "拣货任务已存在，不能重复创建") from exc
    return serialize_shipment(shipment)


@shipment_router.post("/{shipment_id}/scan")
def scan_shipment(
    shipment_id: str,
    payload: ScanRequest,
    principal: Principal = Depends(require_permission("fulfillment:verify")),
    db: Session = Depends(get_db),
) -> dict:
    shipment = db.scalar(
        select(Shipment)
        .where(Shipment.tenant_id == principal.tenant_id, Shipment.id == shipment_id)
        .options(selectinload(Shipment.items))
    )
    if not shipment:
        raise HTTPException(404, "拣货任务不存在")
    if shipment.status != "PICKING":
        raise HTTPException(409, "拣货任务已结束，不能继续扫码")
    barcode = payload.barcode.strip()
    if payload.scan_type == "ORDER":
        if barcode not in {shipment.order.erp_order_no, shipment.order.package_id}:
            raise HTTPException(409, "订单条码不匹配")
        shipment.order_scanned_at = datetime.now(UTC)
    else:
        item = next(
            (
                candidate
                for candidate in shipment.items
                if barcode in {candidate.barcode, candidate.sku_code}
                and candidate.verified_quantity < candidate.expected_quantity
            ),
            None,
        )
        if not item:
            raise HTTPException(409, "商品条码不匹配或数量已扫满")
        item.verified_quantity += 1
    db.commit()
    return serialize_shipment(shipment)


@shipment_router.post("/{shipment_id}/verify")
def verify_shipment(
    shipment_id: str,
    principal: Principal = Depends(require_permission("fulfillment:verify")),
    db: Session = Depends(get_db),
) -> dict:
    shipment = db.scalar(
        select(Shipment)
        .where(Shipment.tenant_id == principal.tenant_id, Shipment.id == shipment_id)
        .options(selectinload(Shipment.items))
    )
    if not shipment:
        raise HTTPException(404, "拣货任务不存在")
    if shipment.status != "PICKING":
        raise HTTPException(409, "拣货任务状态不允许验货确认")
    if not shipment.order_scanned_at:
        raise HTTPException(409, "验货前必须扫描订单条码")
    if any(
        item.verified_quantity != item.expected_quantity for item in shipment.items
    ):
        raise HTTPException(409, "商品验货数量不完整，不能确认")
    shipment.status = "VERIFIED"
    shipment.verified_by = principal.user_id
    shipment.verified_at = datetime.now(UTC)
    db.commit()
    return serialize_shipment(shipment)


@shipment_router.post("/{shipment_id}/ship")
def ship_shipment(
    shipment_id: str,
    principal: Principal = Depends(require_permission("fulfillment:verify")),
    db: Session = Depends(get_db),
) -> dict:
    shipment = db.scalar(
        select(Shipment)
        .where(Shipment.tenant_id == principal.tenant_id, Shipment.id == shipment_id)
        .options(selectinload(Shipment.items), selectinload(Shipment.order))
    )
    if not shipment:
        raise HTTPException(404, "拣货任务不存在")
    if shipment.status != "VERIFIED":
        raise HTTPException(409, "必须先通过扫码验货才能确认出库")
    try:
        consume_shipment_inventory(db, shipment, principal.user_id)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(409, str(exc) or "出库事务失败") from exc
    return serialize_shipment(shipment)
