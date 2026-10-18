from fastapi import APIRouter, Depends, HTTPException
from passlib.hash import pbkdf2_sha256
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bootstrap import ensure_development_data
from ..database import get_db
from ..models import Tenant, User
from ..security import Principal, create_token, get_principal

router = APIRouter(prefix="/auth", tags=["登录鉴权"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    ensure_development_data(db)
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not pbkdf2_sha256.verify(payload.password, user.password_hash):
        raise HTTPException(401, "账号或密码错误")
    tenant = db.get(Tenant, user.tenant_id)
    principal = Principal(user_id=user.id, tenant_id=user.tenant_id, email=user.email)
    return {
        "access_token": create_token(principal),
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.display_name, "email": user.email},
        "tenant": {"id": tenant.id, "name": tenant.name},
    }


@router.get("/me")
def me(principal: Principal = Depends(get_principal)) -> Principal:
    return principal
