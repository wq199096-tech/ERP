from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import get_settings

bearer = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    user_id: str
    tenant_id: str
    email: str


def create_token(principal: Principal) -> str:
    payload = principal.model_dump() | {"exp": datetime.now(UTC) + timedelta(hours=12)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def get_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录")
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().jwt_secret, algorithms=["HS256"]
        )
        return Principal.model_validate(payload)
    except (JWTError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录状态无效或已过期") from exc
