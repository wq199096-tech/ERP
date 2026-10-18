import csv
import hashlib
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from openpyxl import load_workbook
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..adapters import MockPlatformAdapter
from ..adapters.base import UnifiedItem, UnifiedOrder
from ..bootstrap import ensure_development_data
from ..config import get_settings
from ..database import get_db
from ..models import Order, OrderItem, OrderPrivateData, PrintJob, Shop
from ..privacy import decrypt_private, encrypt_private, mask_address, mask_name, mask_phone
from ..security import Principal, require_permission

router = APIRouter(prefix="/orders", tags=["统一订单中心"])
settings = get_settings()


class BatchRequest(BaseModel):
    order_ids: list[str] = Field(min_length=1, max_length=1000)


class PrintPrepareRequest(BaseModel):
    order_ids: list[str] = Field(min_length=1, max_length=100)
    job_types: list[
        Literal["WAYBILL", "MANIFEST_A4", "MANIFEST_A5", "MANIFEST_80", "PRODUCT_LABEL"]
    ] = Field(default=["WAYBILL"], min_length=1, max_length=5)
    printer_name: str = Field(min_length=1, max_length=255)
    operation: Literal["NORMAL", "REPRINT"] = "NORMAL"


class PrintReceiptRequest(BaseModel):
    agent_job_id: str = Field(min_length=1, max_length=100)
    status: Literal["ACKNOWLEDGED", "RENDERED", "SUBMITTED", "PRINTED", "FAILED", "UNKNOWN"]
    waybill_no: str | None = Field(default=None, max_length=100)
    system_job_id: str | None = Field(default=None, max_length=100)
    output_file: str | None = Field(default=None, max_length=500)
    error_message: str | None = Field(default=None, max_length=2000)


def _erp_order_number(tenant_id: str, incoming: UnifiedOrder) -> str:
    source = f"{tenant_id}:{incoming.platform}:{incoming.shop_id}:{incoming.platform_order_no}"
    digest = hashlib.sha256(source.encode()).hexdigest()[:20].upper()
    return f"SO{incoming.created_at:%Y%m%d}{digest}"


def _print_blockers(order: Order, *, require_audit: bool = True) -> list[str]:
    blockers: list[str] = []
    if order.status in {"CANCELLED", "REFUNDED"}:
        blockers.append("订单已取消或退款")
    elif order.status != "PENDING_SHIPMENT":
        blockers.append("订单不是待发货状态")
    if order.after_sale_status != "NONE":
        blockers.append("订单存在退款或售后")
    if require_audit and order.audit_status != "APPROVED":
        blockers.append("订单尚未审核")
    if not order.address_valid:
        blockers.append("收货地址异常")
    if not order.stock_available:
        blockers.append("库存不足")
    if any(not item.internal_sku for item in order.items):
        blockers.append("存在未映射 SKU")
    return blockers


def serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "platform": order.platform,
        "shop_id": order.shop_id,
        "platform_order_no": order.platform_order_no,
        "erp_order_no": order.erp_order_no,
        "version": order.version,
        "package_id": order.package_id,
        "status": order.status,
        "after_sale_status": order.after_sale_status,
        "audit_status": order.audit_status,
        "print_status": order.print_status,
        "print_blockers": _print_blockers(order),
        "receiver_name": order.receiver_name,
        "receiver_phone_masked": order.receiver_phone_masked,
        "receiver_address_masked": order.receiver_address_masked,
        "warehouse_name": order.warehouse_name,
        "paid_amount": str(order.paid_amount),
        "discount_amount": str(order.discount_amount),
        "remark": order.remark,
        "paid_at": order.paid_at,
        "created_at": order.created_at,
        "items": [
            {
                "id": item.id,
                "platform_sku": item.platform_sku,
                "internal_sku": item.internal_sku,
                "product_name": item.product_name,
                "specification": item.specification,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "barcode": item.barcode,
            }
            for item in order.items
        ],
    }


def upsert_unified(db: Session, tenant_id: str, incoming: UnifiedOrder) -> tuple[Order, bool]:
    order = db.scalar(
        select(Order).where(
            Order.tenant_id == tenant_id,
            Order.platform == incoming.platform,
            Order.shop_id == incoming.shop_id,
            Order.platform_order_no == incoming.platform_order_no,
        )
    )
    created = order is None
    if order is None:
        order = Order(
            tenant_id=tenant_id,
            shop_id=incoming.shop_id,
            platform=incoming.platform,
            platform_order_no=incoming.platform_order_no,
            erp_order_no=_erp_order_number(tenant_id, incoming),
            status=incoming.status,
            after_sale_status=incoming.after_sale_status,
            receiver_name=mask_name(incoming.receiver_name),
            receiver_phone_masked=mask_phone(incoming.receiver_phone_masked),
            receiver_address_masked=mask_address(incoming.receiver_address_masked),
            warehouse_name="杭州一号仓",
            package_id=f"PKG-{incoming.platform}-{incoming.platform_order_no[-12:]}",
            address_valid=len(incoming.receiver_address_masked.strip()) >= 8,
            stock_available=True,
            paid_amount=incoming.paid_amount,
            discount_amount=incoming.discount_amount,
            paid_at=incoming.paid_at,
            created_at=incoming.created_at,
            remark=incoming.remark,
        )
        for item in incoming.items:
            order.items.append(
                OrderItem(
                    tenant_id=tenant_id,
                    platform_sku=item.platform_sku,
                    internal_sku=item.internal_sku,
                    product_name=item.product_name,
                    specification=item.specification,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    barcode=item.barcode,
                )
            )
        db.add(order)
        db.flush()
        db.add(
            OrderPrivateData(
                tenant_id=tenant_id,
                order_id=order.id,
                receiver_name_encrypted=encrypt_private(incoming.receiver_name),
                receiver_phone_encrypted=encrypt_private(incoming.receiver_phone_masked),
                receiver_address_encrypted=encrypt_private(incoming.receiver_address_masked),
            )
        )
    else:
        new_masked_address = mask_address(incoming.receiver_address_masked)
        requires_review = (
            order.status != incoming.status
            or order.after_sale_status != incoming.after_sale_status
            or order.receiver_address_masked != new_masked_address
        )
        order.status = incoming.status
        order.after_sale_status = incoming.after_sale_status
        order.receiver_name = mask_name(incoming.receiver_name)
        order.receiver_phone_masked = mask_phone(incoming.receiver_phone_masked)
        order.receiver_address_masked = new_masked_address
        order.address_valid = len(incoming.receiver_address_masked.strip()) >= 8
        private = db.scalar(select(OrderPrivateData).where(OrderPrivateData.order_id == order.id))
        if private:
            private.receiver_name_encrypted = encrypt_private(incoming.receiver_name)
            private.receiver_phone_encrypted = encrypt_private(incoming.receiver_phone_masked)
            private.receiver_address_encrypted = encrypt_private(incoming.receiver_address_masked)
        if requires_review:
            order.audit_status = "PENDING"
            order.version += 1
    return order, created


@router.post("/mock/sync")
def sync_mock(
    count: int = Query(1000, ge=1, le=10000),
    principal: Principal = Depends(require_permission("orders:audit")),
    db: Session = Depends(get_db),
) -> dict:
    if settings.is_production or not settings.enable_demo_data:
        raise HTTPException(404, "模拟数据功能未启用")
    ensure_development_data(db)
    created_count = 0
    updated_count = 0
    for incoming in MockPlatformAdapter().fetch_orders(count):
        _, created = upsert_unified(db, principal.tenant_id, incoming)
        created_count += int(created)
        updated_count += int(not created)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "订单同步发生幂等冲突，请重试") from exc
    return {"received": count, "created": created_count, "updated": updated_count}


@router.get("")
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    platform: str | None = None,
    shop_id: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    principal: Principal = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
) -> dict:
    conditions = [Order.tenant_id == principal.tenant_id]
    if platform:
        conditions.append(Order.platform == platform)
    if shop_id:
        conditions.append(Order.shop_id == shop_id)
    if status:
        conditions.append(Order.status == status)
    if keyword:
        term = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                Order.platform_order_no.ilike(term),
                Order.erp_order_no.ilike(term),
                Order.items.any(OrderItem.product_name.ilike(term)),
                Order.items.any(OrderItem.internal_sku.ilike(term)),
            )
        )
    total = db.scalar(select(func.count()).select_from(Order).where(*conditions)) or 0
    orders = db.scalars(
        select(Order)
        .where(*conditions)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    shop_names = {shop.id: shop.name for shop in db.scalars(select(Shop)).all()}
    records = []
    for order in orders:
        record = serialize_order(order)
        record["shop_name"] = shop_names.get(order.shop_id, "未知店铺")
        records.append(record)
    return {"records": records, "total": total, "page": page, "page_size": page_size}


@router.post("/batch/audit")
def batch_audit(
    payload: BatchRequest,
    principal: Principal = Depends(require_permission("orders:audit")),
    db: Session = Depends(get_db),
) -> dict:
    orders = db.scalars(
        select(Order).where(Order.tenant_id == principal.tenant_id, Order.id.in_(payload.order_ids))
    ).all()
    updated = 0
    blocked: dict[str, list[str]] = {}
    for order in orders:
        reasons = _print_blockers(order, require_audit=False)
        if reasons:
            blocked[order.id] = reasons
            continue
        order.audit_status = "APPROVED"
        updated += 1
    db.commit()
    return {"updated": updated, "blocked": blocked}


@router.post("/print/prepare")
def prepare_print_jobs(
    payload: PrintPrepareRequest,
    principal: Principal = Depends(require_permission("orders:print")),
    db: Session = Depends(get_db),
) -> dict:
    orders = db.scalars(
        select(Order).where(Order.tenant_id == principal.tenant_id, Order.id.in_(payload.order_ids))
    ).all()
    found_ids = {order.id for order in orders}
    blocked: dict[str, list[str]] = {
        order_id: ["订单不存在或不属于当前企业"]
        for order_id in payload.order_ids
        if order_id not in found_ids
    }
    tasks: list[PrintJob] = []
    for order in orders:
        reasons = _print_blockers(order)
        if reasons:
            blocked[order.id] = reasons
            continue
        for job_type in dict.fromkeys(payload.job_types):
            reuse_waybill_no = None
            if payload.operation == "REPRINT":
                previous = db.scalar(
                    select(PrintJob)
                    .where(
                        PrintJob.tenant_id == principal.tenant_id,
                        PrintJob.order_id == order.id,
                        PrintJob.job_type == job_type,
                        PrintJob.waybill_no.is_not(None),
                    )
                    .order_by(PrintJob.created_at.desc())
                )
                if job_type == "WAYBILL" and not previous:
                    blocked[order.id] = ["补打必须复用已存在的运单号"]
                    continue
                reuse_waybill_no = previous.waybill_no if previous else None
                idempotency_key = (
                    f"{order.id}:{order.version}:{order.package_id}:"
                    f"{job_type}:REPRINT:{uuid.uuid4()}"
                )
            else:
                idempotency_key = f"{order.id}:{order.version}:{order.package_id}:{job_type}:NORMAL"
                existing = db.scalar(
                    select(PrintJob).where(
                        PrintJob.tenant_id == principal.tenant_id,
                        PrintJob.idempotency_key == idempotency_key,
                    )
                )
                if existing:
                    tasks.append(existing)
                    continue
            task = PrintJob(
                tenant_id=principal.tenant_id,
                idempotency_key=idempotency_key,
                order_id=order.id,
                erp_order_no=order.erp_order_no,
                order_version=order.version,
                package_id=order.package_id,
                operation=payload.operation,
                job_type=job_type,
                printer_name=payload.printer_name,
                payload={
                    "data_source": "SERVER_ORDER",
                    "server_task_id": None,
                    "erp_order_no": order.erp_order_no,
                    "order_version": order.version,
                    "package_id": order.package_id,
                    "job_type": job_type,
                    "operation": payload.operation,
                    "printer_name": payload.printer_name,
                    "reuse_waybill_no": reuse_waybill_no,
                    "receiver_name": order.receiver_name,
                    "receiver_phone": order.receiver_phone_masked,
                    "receiver_address": order.receiver_address_masked,
                    "warehouse_name": order.warehouse_name,
                    "remark": order.remark,
                    "items": [
                        {
                            "internal_sku": item.internal_sku,
                            "product_name": item.product_name,
                            "specification": item.specification,
                            "quantity": item.quantity,
                            "barcode": item.barcode,
                        }
                        for item in order.items
                    ],
                },
            )
            db.add(task)
            db.flush()
            task.payload = task.payload | {"server_task_id": task.id}
            tasks.append(task)
            order.print_status = "QUEUED"
    db.commit()
    return {
        "tasks": [
            {
                "id": task.id,
                "idempotency_key": task.idempotency_key,
                "status": task.status,
                "payload": task.payload,
            }
            for task in tasks
        ],
        "blocked": blocked,
    }


@router.post("/print/tasks/{task_id}/receipt")
def print_receipt(
    task_id: str,
    payload: PrintReceiptRequest,
    principal: Principal = Depends(require_permission("orders:print")),
    db: Session = Depends(get_db),
) -> dict:
    task = db.scalar(
        select(PrintJob).where(PrintJob.id == task_id, PrintJob.tenant_id == principal.tenant_id)
    )
    if not task:
        raise HTTPException(404, "打印任务不存在")
    if task.status == "PRINTED":
        raise HTTPException(409, "任务已完成出纸，不能重复回执")
    if task.agent_job_id and task.agent_job_id != payload.agent_job_id:
        raise HTTPException(409, "回执的 Agent 作业标识与任务不一致")
    if task.waybill_no and payload.waybill_no and task.waybill_no != payload.waybill_no:
        raise HTTPException(409, "回执运单号与任务已有运单号不一致")
    transitions = {
        "CREATED": {"ACKNOWLEDGED", "RENDERED", "SUBMITTED", "PRINTED", "FAILED", "UNKNOWN"},
        "ACKNOWLEDGED": {"RENDERED", "SUBMITTED", "PRINTED", "FAILED", "UNKNOWN"},
        "RENDERED": {"SUBMITTED", "PRINTED", "FAILED", "UNKNOWN"},
        "SUBMITTED": {"PRINTED", "FAILED", "UNKNOWN"},
        "FAILED": {"ACKNOWLEDGED", "RENDERED", "SUBMITTED", "PRINTED", "FAILED", "UNKNOWN"},
        "UNKNOWN": {"ACKNOWLEDGED", "RENDERED", "SUBMITTED", "PRINTED", "FAILED", "UNKNOWN"},
    }
    if payload.status not in transitions.get(task.status, set()):
        raise HTTPException(409, f"打印任务状态不允许从 {task.status} 转换到 {payload.status}")
    task.agent_job_id = payload.agent_job_id
    task.status = payload.status
    task.waybill_no = payload.waybill_no or task.waybill_no
    task.system_job_id = payload.system_job_id or task.system_job_id
    task.output_file = payload.output_file or task.output_file
    task.error_message = payload.error_message
    order = db.get(Order, task.order_id)
    if order:
        statuses = set(
            db.scalars(
                select(PrintJob.status).where(
                    PrintJob.order_id == task.order_id,
                    PrintJob.order_version == task.order_version,
                    PrintJob.package_id == task.package_id,
                )
            ).all()
        )
        if "FAILED" in statuses:
            order.print_status = "FAILED"
        elif "UNKNOWN" in statuses:
            order.print_status = "VERIFY_REQUIRED"
        elif statuses == {"PRINTED"}:
            order.print_status = "PRINTED"
        elif statuses.issubset({"SUBMITTED", "PRINTED"}):
            order.print_status = "SUBMITTED"
        else:
            order.print_status = "PROCESSING"
    db.commit()
    return {
        "task_id": task.id,
        "status": task.status,
        "order_print_status": order.print_status if order else None,
    }


@router.get("/private/{order_id}")
def private_order_data(
    order_id: str,
    principal: Principal = Depends(require_permission("private:read")),
    db: Session = Depends(get_db),
) -> dict:
    private = db.scalar(
        select(OrderPrivateData).where(
            OrderPrivateData.order_id == order_id,
            OrderPrivateData.tenant_id == principal.tenant_id,
        )
    )
    if not private:
        raise HTTPException(404, "订单敏感信息不存在")
    return {
        "receiver_name": decrypt_private(private.receiver_name_encrypted),
        "receiver_phone": decrypt_private(private.receiver_phone_encrypted),
        "receiver_address": decrypt_private(private.receiver_address_encrypted),
    }


@router.get("/{order_id}")
def order_detail(
    order_id: str,
    principal: Principal = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
) -> dict:
    order = db.scalar(
        select(Order).where(Order.id == order_id, Order.tenant_id == principal.tenant_id)
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    return serialize_order(order)


def _rows_from_upload(filename: str, content: bytes) -> list[dict[str, str]]:
    if len(content) > settings.max_import_bytes:
        raise HTTPException(413, f"导入文件不得超过 {settings.max_import_bytes} 字节")
    if filename.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    elif filename.lower().endswith((".xlsx", ".xlsm")):
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        values = list(workbook.active.iter_rows(values_only=True))
        if not values:
            return []
        headers = [str(value or "").strip() for value in values[0]]
        rows = [
            dict(zip(headers, ("" if value is None else str(value) for value in row), strict=False))
            for row in values[1:]
        ]
    else:
        raise HTTPException(415, "仅支持 CSV 或 XLSX 文件")
    if len(rows) > settings.max_import_rows:
        raise HTTPException(413, f"导入数据不得超过 {settings.max_import_rows} 行")
    required = {"平台订单号", "商品名称", "数量", "实付金额"}
    if rows and not required.issubset(rows[0]):
        missing = "、".join(sorted(required - set(rows[0])))
        raise HTTPException(422, f"缺少必填字段：{missing}")
    return rows


@router.post("/import")
async def import_orders(
    file: UploadFile = File(...),
    principal: Principal = Depends(require_permission("orders:audit")),
    db: Session = Depends(get_db),
) -> dict:
    rows = _rows_from_upload(file.filename or "", await file.read(settings.max_import_bytes + 1))
    shop = db.scalar(select(Shop).where(Shop.tenant_id == principal.tenant_id))
    if not shop:
        raise HTTPException(422, "当前企业尚未配置店铺")
    created = 0
    errors: list[dict] = []
    for line, row in enumerate(rows, start=2):
        try:
            amount = Decimal(str(row.get("实付金额", "0")))
            quantity = int(str(row.get("数量", "1")))
            if amount < 0 or amount > Decimal("999999999999.99"):
                raise ValueError("实付金额超出允许范围")
            if quantity < 1 or quantity > 100000:
                raise ValueError("数量必须在 1 到 100000 之间")
            order_no = str(row["平台订单号"]).strip()
            if not order_no or len(order_no) > 100:
                raise ValueError("平台订单号为空或过长")
            incoming = UnifiedOrder(
                platform=str(row.get("平台") or "CSV").upper()[:30],
                shop_id=shop.id,
                platform_order_no=order_no,
                status=str(row.get("订单状态") or "PENDING_SHIPMENT")[:30],
                after_sale_status="NONE",
                receiver_name=str(row.get("收件人") or "未提供")[:80],
                receiver_phone_masked=str(row.get("手机号") or "***")[:30],
                receiver_address_masked=str(row.get("地址") or "未提供")[:500],
                paid_amount=amount,
                discount_amount=Decimal("0"),
                paid_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                remark=str(row.get("备注") or "")[:2000],
                items=(
                    UnifiedItem(
                        platform_sku=str(row.get("平台SKU") or row.get("SKU") or "UNMAPPED")[:100],
                        internal_sku=str(row.get("SKU") or "").strip()[:100] or None,
                        product_name=str(row.get("商品名称") or "未命名商品")[:255],
                        specification=str(row.get("规格") or "")[:120],
                        quantity=quantity,
                        unit_price=amount,
                        barcode=str(row.get("条码") or "")[:80],
                    ),
                ),
            )
            _, was_created = upsert_unified(db, principal.tenant_id, incoming)
            created += int(was_created)
        except (KeyError, ValueError, InvalidOperation) as exc:
            errors.append({"line": line, "message": str(exc)})
    db.commit()
    return {"rows": len(rows), "created": created, "errors": errors[:100]}
