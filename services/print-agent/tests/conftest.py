import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="smartorder-agent-tests-"))
os.environ["PRINT_AGENT_DB"] = str(TEST_ROOT / "agent.sqlite3")
os.environ["PRINT_AGENT_OUTPUT"] = str(TEST_ROOT / "output")
os.environ["PRINT_AGENT_TOKEN"] = "test-agent-token-stage31"
os.environ["APP_ENV"] = "development"
