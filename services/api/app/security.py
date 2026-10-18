from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    role: str = "viewer"


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "orders:read", "orders:audit", "orders:print", "private:read",
        "inventory:read", "inventory:write", "fulfillment:verify",
    },
    "operator": {
        "orders:read", "orders:print", "inventory:read", "inventory:write",
        "fulfillment:verify",
    },
    "auditor": {"orders:read", "orders:audit", "inventory:read"},
    "viewer": {"orders:read", "inventory:read"},
}


def create_token(principal: Principal) -> str:
    payload = principal.model_dump() | {"exp": datetime.now(UTC) + timedelta(hours=12)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录")
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().jwt_secret, algorithms=["HS256"]
        )
        principal = Principal.model_validate(payload)
    except (JWTError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录状态无效或已过期") from exc
    user = db.get(User, principal.user_id)
    if (
        not user
        or not user.is_active
        or user.tenant_id != principal.tenant_id
        or user.email != principal.email
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户已失效或不属于当前企业")
    principal.role = user.role
    return principal


def require_permission(permission: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if permission not in ROLE_PERMISSIONS.get(principal.role, set()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "当前角色没有执行此操作的权限")
        return principal

    return dependency
