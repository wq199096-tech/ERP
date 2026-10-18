from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bootstrap import ensure_development_data
from ..database import get_db
from ..models import Shop
from ..security import Principal, get_principal

router = APIRouter(prefix="/shops", tags=["店铺管理"])


@router.get("")
def list_shops(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[dict]:
    ensure_development_data(db)
    shops = db.scalars(select(Shop).where(Shop.tenant_id == principal.tenant_id)).all()
    return [
        {
            "id": shop.id,
            "name": shop.name,
            "platform": shop.platform,
            "status": shop.status,
            "capability": "MOCK_ONLY",
        }
        for shop in shops
    ]
