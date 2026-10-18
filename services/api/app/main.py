from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from . import models  # noqa: F401
from .config import get_settings
from .database import Base, engine, get_db
from .routers import auth, dashboard, orders, shops

settings = get_settings()
app = FastAPI(title="智单 ERP API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.database_url.startswith("sqlite"):
    Base.metadata.create_all(engine)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(shops.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["system"])
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise HTTPException(503, "数据库健康检查失败") from exc
    return {"status": "ok", "service": "smartorder-api", "environment": settings.app_env}
