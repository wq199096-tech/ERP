from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401
from .config import get_settings
from .database import Base, engine

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


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "smartorder-api", "environment": settings.app_env}

