import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text

from alembic import command
from alembic.config import Config

API_ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith("postgresql+psycopg://")
ISOLATED_TEST_DATABASE = "erp_stage34_test"

if IS_POSTGRES:
    # PostgreSQL integration tests receive their URL from the CI environment.  Never
    # replace it with SQLite here: doing so turns an integration job into a no-op.
    from sqlalchemy.engine import make_url

    database_name = make_url(DATABASE_URL).database
    assert database_name == ISOLATED_TEST_DATABASE, (
        "PostgreSQL 集成测试只允许使用 erp_stage34_test 隔离数据库"
    )
    TEST_ROOT = Path(tempfile.mkdtemp(prefix="smartorder-api-postgres-tests-"))
else:
    TEST_ROOT = Path(tempfile.mkdtemp(prefix="smartorder-api-tests-"))
    TEST_DATABASE = TEST_ROOT / "isolated.sqlite3"
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["APP_ENV"] = "development"
os.environ["ENABLE_DEMO_DATA"] = "true"

from app import models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402

collect_ignore_glob = [] if IS_POSTGRES else ["test_postgres_*.py"]


def _alembic_config() -> Config:
    config = Config(API_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return config


def _reset_postgres_schema() -> None:
    # make_url() above already refuses anything but erp_stage34_test.  Downgrade +
    # upgrade only affects the disposable service-container database and prevents an
    # existing alembic_version row from turning upgrade(head) into a no-op after cleanup.
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    with engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        assert database == ISOLATED_TEST_DATABASE


@pytest.fixture(autouse=True)
def isolated_database():
    if IS_POSTGRES:
        _reset_postgres_schema()
    else:
        assert TEST_ROOT in TEST_DATABASE.parents
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    yield
