from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    InventoryBalance,
    InventoryReservation,
    Order,
    OrderItem,
    ProductSku,
    ProductSkuMapping,
    Shipment,
    StockMovement,
)


def resolve_order_item_sku(db: Session, tenant_id: str, item: OrderItem) -> ProductSku | None:
    if item.internal_sku:
        sku = db.scalar(
            select(ProductSku).where(
                ProductSku.tenant_id == tenant_id,
                ProductSku.sku_code == item.internal_sku,
                ProductSku.status == "ACTIVE",
            )
        )
        if sku:
            return sku
    return db.scalar(
        select(ProductSku)
        .join(ProductSkuMapping, ProductSkuMapping.sku_id == ProductSku.id)
        .where(
            ProductSkuMapping.tenant_id == tenant_id,
            ProductSkuMapping.platform == item.order.platform,
            ProductSkuMapping.shop_id == item.order.shop_id,
            ProductSkuMapping.platform_sku == item.platform_sku,
            ProductSkuMapping.status == "ACTIVE",
            ProductSku.status == "ACTIVE",
        )
    )


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


def _add_movement(
    db: Session,
    *,
    tenant_id: str,
    warehouse_id: str,
    sku_id: str,
    movement_type: str,
    quantity: int,
    balance_after: int,
    movement_key: str,
    operator_id: str,
    order_id: str | None = None,
    reservation_id: str | None = None,
    note: str = "",
) -> None:
    db.add(
        StockMovement(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            movement_type=movement_type,
            quantity=quantity,
            balance_after=balance_after,
            movement_key=movement_key,
            operator_id=operator_id,
            order_id=order_id,
            reservation_id=reservation_id,
            note=note,
        )
    )


def _reserve_order(
    db: Session, order: Order, warehouse_id: str, operator_id: str
) -> list[str]:
    reasons: list[str] = []
    resolved: list[tuple[OrderItem, ProductSku]] = []
    for item in order.items:
        sku = resolve_order_item_sku(db, order.tenant_id, item)
        if not sku:
            reasons.append(f"SKU 未映射：{item.platform_sku or item.product_name}")
            continue
        resolved.append((item, sku))

    warehouse = db.scalar(
        select_by_warehouse_active(order.tenant_id, warehouse_id)
    )
    if warehouse is None:
        reasons.append("出库仓库不存在或已停用")

    if reasons:
        return reasons

    for item, sku in resolved:
        existing = db.scalar(
            select(InventoryReservation).where(
                InventoryReservation.tenant_id == order.tenant_id,
                InventoryReservation.order_item_id == item.id,
            )
        )
        if existing:
            if existing.status != "ACTIVE":
                reasons.append("订单项已有历史库存预留，不能重复预留")
            continue
        balance = _locked_balance(db, order.tenant_id, warehouse_id, sku.id)
        if balance is None:
            reasons.append(f"SKU 在当前仓库没有库存：{sku.sku_code}")
            continue
        available = balance.on_hand - balance.reserved
        if available < item.quantity:
            reasons.append(f"库存不足：{sku.sku_code} 可用 {available}，需 {item.quantity}")
            continue

        reservation = InventoryReservation(
            tenant_id=order.tenant_id,
            order_id=order.id,
            order_item_id=item.id,
            sku_id=sku.id,
            warehouse_id=warehouse_id,
            quantity=item.quantity,
        )
        db.add(reservation)
        db.flush()
        balance.reserved += item.quantity
        item.internal_sku = sku.sku_code
        if not item.barcode:
            item.barcode = sku.barcode
        _add_movement(
            db,
            tenant_id=order.tenant_id,
            warehouse_id=warehouse_id,
            sku_id=sku.id,
            movement_type="RESERVED",
            quantity=item.quantity,
            balance_after=balance.on_hand - balance.reserved,
            movement_key=f"RESERVE:{reservation.id}",
            operator_id=operator_id,
            order_id=order.id,
            reservation_id=reservation.id,
            note=f"订单审核预留 {order.erp_order_no}",
        )

    if reasons:
        return reasons

    order.warehouse_id = warehouse_id
    order.stock_available = True
    return []


def select_by_warehouse_active(tenant_id: str, warehouse_id: str):
    from .models import Warehouse

    return select(Warehouse).where(
        Warehouse.tenant_id == tenant_id,
        Warehouse.id == warehouse_id,
        Warehouse.status == "ACTIVE",
    )


def reserve_order(db: Session, order: Order, warehouse_id: str, operator_id: str) -> list[str]:
    nested = db.begin_nested()
    reasons = _reserve_order(db, order, warehouse_id, operator_id)
    if reasons:
        nested.rollback()
        order.stock_available = False
    else:
        nested.commit()
    return reasons


def release_order_reservations(db: Session, order: Order, operator_id: str) -> int:
    reservations = db.scalars(
        select(InventoryReservation).where(
            InventoryReservation.tenant_id == order.tenant_id,
            InventoryReservation.order_id == order.id,
            InventoryReservation.status == "ACTIVE",
        )
    ).all()
    now = datetime.now(UTC)
    for reservation in reservations:
        balance = _locked_balance(
            db, order.tenant_id, reservation.warehouse_id, reservation.sku_id
        )
        if balance:
            balance.reserved = max(0, balance.reserved - reservation.quantity)
            balance.updated_at = now
            _add_movement(
                db,
                tenant_id=order.tenant_id,
                warehouse_id=reservation.warehouse_id,
                sku_id=reservation.sku_id,
                movement_type="RELEASE",
                quantity=-reservation.quantity,
                balance_after=balance.on_hand - balance.reserved,
                movement_key=f"RELEASE:{reservation.id}",
                operator_id=operator_id,
                order_id=order.id,
                reservation_id=reservation.id,
                note=f"取消订单释放预留 {order.erp_order_no}",
            )
        reservation.status = "RELEASED"
        reservation.released_at = now
    return len(reservations)


def consume_shipment_inventory(db: Session, shipment: Shipment, operator_id: str) -> None:
    order = shipment.order
    now = datetime.now(UTC)
    for item in shipment.items:
        reservation = db.scalar(
            select(InventoryReservation).where(
                InventoryReservation.tenant_id == shipment.tenant_id,
                InventoryReservation.order_item_id == item.order_item_id,
                InventoryReservation.status == "ACTIVE",
            )
        )
        if not reservation or reservation.quantity != item.expected_quantity:
            raise ValueError("库存预留缺失或与验货数量不一致")
        if reservation.sku_id != item.sku_id or reservation.warehouse_id != shipment.warehouse_id:
            raise ValueError("库存预留与出库仓库或商品不一致")
        balance = _locked_balance(
            db, shipment.tenant_id, shipment.warehouse_id, item.sku_id
        )
        if not balance or balance.reserved < item.expected_quantity:
            raise ValueError("库存预留余额不足")
        balance.on_hand -= item.expected_quantity
        balance.reserved -= item.expected_quantity
        _add_movement(
            db,
            tenant_id=shipment.tenant_id,
            warehouse_id=shipment.warehouse_id,
            sku_id=item.sku_id,
            movement_type="OUTBOUND",
            quantity=-item.expected_quantity,
            balance_after=balance.on_hand,
            movement_key=f"OUTBOUND:{item.id}",
            operator_id=operator_id,
            order_id=shipment.order_id,
            reservation_id=reservation.id,
            note=f"订单出库 {order.erp_order_no}",
        )
        reservation.status = "CONSUMED"
        reservation.updated_at = now
    shipment.status = "SHIPPED"
    shipment.shipped_by = operator_id
    shipment.shipped_at = now
    order.status = "SHIPPED"
