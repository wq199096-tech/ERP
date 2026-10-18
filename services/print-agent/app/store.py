import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FINAL_STATES = {"PRINTED", "CANCELLED"}
RETRYABLE_STATES = {"FAILED", "UNKNOWN"}


class PrintStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS print_jobs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    job_type TEXT NOT NULL,
                    printer_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    output_file TEXT,
                    waybill_no TEXT,
                    system_job_id TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS print_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES print_jobs(id)
                );
                CREATE TABLE IF NOT EXISTS agent_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS print_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES print_jobs(id)
                );
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(print_jobs)")}
            if "system_job_id" not in columns:
                db.execute("ALTER TABLE print_jobs ADD COLUMN system_job_id TEXT")

    def recover_interrupted(self) -> int:
        now = datetime.now(UTC).isoformat()
        submitted_message = "Agent 重启时任务可能已提交，必须人工核验后重试"
        unsubmitted_message = "Agent 重启时任务尚未提交，可安全重试"
        retained_message = "Agent 重启后继续保持状态未知，等待人工核验"
        changed = 0
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, status, system_job_id FROM print_jobs
                WHERE status IN (
                    'CREATED', 'QUEUED', 'RENDERED', 'SUBMITTING', 'SUBMITTED', 'UNKNOWN'
                )"""
            ).fetchall()
            for row in rows:
                status = row["status"]
                if status == "UNKNOWN":
                    new_status = "UNKNOWN"
                    message = retained_message
                elif status == "SUBMITTING" or row["system_job_id"] or status == "SUBMITTED":
                    new_status = "UNKNOWN"
                    message = submitted_message
                else:
                    new_status = "FAILED"
                    message = unsubmitted_message
                if status != new_status or status == "UNKNOWN":
                    db.execute(
                        "UPDATE print_jobs SET status = ?, error_message = ?, updated_at = ? "
                        "WHERE id = ?",
                        (new_status, message, now, row["id"]),
                    )
                    db.execute(
                        "INSERT INTO print_attempts "
                        "(job_id, status, message, created_at) VALUES (?, ?, ?, ?)",
                        (row["id"], new_status, message, now),
                    )
                if status != new_status:
                    changed += 1
        return changed

    def set_queue_paused(self, paused: bool) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO agent_state (key, value) VALUES ('queue_paused', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("1" if paused else "0",),
            )

    def is_queue_paused(self) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT value FROM agent_state WHERE key = 'queue_paused'").fetchone()
        return bool(row and row["value"] == "1")

    @staticmethod
    def _dict(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["payload"] = json.loads(value["payload"])
        return value

    def get_by_key(self, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM print_jobs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return self._dict(row) if row else None

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._dict(row) if row else None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM print_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._dict(row) for row in rows]

    def list_by_status(self, status: str, limit: int = 1000) -> "list[dict[str, Any]]":
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM print_jobs WHERE status = ? ORDER BY created_at LIMIT ?",
                (status, limit),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def record_audit(self, job_id: str, actor: str, action: str, detail: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            db.execute(
                """INSERT INTO print_audits (job_id, actor, action, detail, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (job_id, actor, action, detail, now),
            )

    def list_attempts(self, job_id: str, limit: int = 50) -> "list[dict[str, str]]":
        with self.connect() as db:
            attempts = db.execute(
                """SELECT status, message, created_at FROM print_attempts
                WHERE job_id = ? ORDER BY id DESC LIMIT ?""",
                (job_id, limit),
            ).fetchall()
        return [dict(row) for row in attempts]

    def create(
        self,
        *,
        idempotency_key: str,
        job_type: str,
        printer_name: str,
        payload: dict,
        waybill_no: str | None,
    ) -> dict[str, Any]:
        existing = self.get_by_key(idempotency_key)
        if existing:
            return existing
        job_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            try:
                db.execute(
                    """INSERT INTO print_jobs
                    (id, idempotency_key, job_type, printer_name, status, payload,
                     waybill_no, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'CREATED', ?, ?, ?, ?)""",
                    (
                        job_id,
                        idempotency_key,
                        job_type,
                        printer_name,
                        json.dumps(payload, ensure_ascii=False),
                        waybill_no,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                pass
        existing = self.get_by_key(idempotency_key)
        return existing if existing else self.get(job_id)

    def transition(
        self,
        job_id: str,
        status: str,
        message: str = "",
        output_file: str | None = None,
        system_job_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            db.execute(
                """UPDATE print_jobs SET status = ?, error_message = ?,
                output_file = COALESCE(?, output_file),
                system_job_id = COALESCE(?, system_job_id), updated_at = ? WHERE id = ?""",
                (status, message or None, output_file, system_job_id, now, job_id),
            )
            db.execute(
                "INSERT INTO print_attempts "
                "(job_id, status, message, created_at) VALUES (?, ?, ?, ?)",
                (job_id, status, message, now),
            )
        return self.get(job_id)
