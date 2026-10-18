from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Order, PrintJob
from ..security import Principal, require_permission

router = APIRouter(prefix="/dashboard", tags=["经营首页"])


@router.get("/summary")
def summary(
    principal: Principal = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
) -> dict:
    tenant = Order.tenant_id == principal.tenant_id
    total = db.scalar(select(func.count()).select_from(Order).where(tenant)) or 0
    pending = (
        db.scalar(
            select(func.count())
            .select_from(Order)
            .where(tenant, Order.status == "PENDING_SHIPMENT")
        )
        or 0
    )
    exceptions = (
        db.scalar(
            select(func.count()).select_from(Order).where(
                tenant,
                (Order.after_sale_status != "NONE")
                | (Order.address_valid.is_(False))
                | (Order.stock_available.is_(False)),
            )
        )
        or 0
    )
    print_counts = dict(
        db.execute(
            select(PrintJob.status, func.count())
            .where(PrintJob.tenant_id == principal.tenant_id)
            .group_by(PrintJob.status)
        ).all()
    )
    return {
        "generated_at": datetime.now(UTC),
        "orders_total": total,
        "pending_shipment": pending,
        "exception_orders": exceptions,
        "print_jobs": print_counts,
        "has_data": total > 0,
    }
