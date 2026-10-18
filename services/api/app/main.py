from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401
from .config import get_settings
from .database import Base, engine
from .routers import auth, orders, shops

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


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "smartorder-api", "environment": settings.app_env}
