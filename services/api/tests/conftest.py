import os
import tempfile
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="smartorder-api-tests-"))
TEST_DATABASE = TEST_ROOT / "isolated.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["APP_ENV"] = "development"
os.environ["ENABLE_DEMO_DATA"] = "true"

from app.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_database():
    assert TEST_ROOT in TEST_DATABASE.parents
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
