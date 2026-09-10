from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3
TERMINAL = {"RELEASE_APPROVED", "FAIL", "BLOCKED"}


class StateError(RuntimeError):
    pass


def _migrate_state(payload: dict[str, Any]) -> dict[str, Any]:
    state = dict(payload)
    version = state.get("schema_version")
    migration_evidence = state.get("migration_evidence")
    if not isinstance(migration_evidence, list):
        migration_evidence = []
        state["migration_evidence"] = migration_evidence
    if version is None:
        state["schema_version"] = SCHEMA_VERSION
        state.setdefault("run_id", str(uuid.uuid4()))
        migration_evidence.append("recognized unversioned state normalized to schema 3")
    elif version == 2:
        state["schema_version"] = SCHEMA_VERSION
        migration_evidence.append(
            "schema 2 state migrated to schema 3 without fabricating stage evidence"
        )
    elif version != SCHEMA_VERSION:
        raise StateError(f"Unsupported state schema version: {version}")
    state.setdefault("pending_stage", state.get("stage", "inspect"))
    state.setdefault("repair_cycles", {})
    state.setdefault("stage_results", [])
    return state


class StateStore:
    @staticmethod
    def read(repository: Path) -> dict[str, Any] | None:
        path = repository.resolve() / ".ai-team" / "state.sqlite3"
        if not path.is_file():
            return None
        try:
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = db.execute("SELECT payload FROM run_state WHERE id=1").fetchone()
            finally:
                db.close()
            state = json.loads(row[0]) if row else None
            return _migrate_state(state) if state else None
        except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
            raise StateError(f"Persisted state is corrupt: {exc}") from exc

    def __init__(self, repository: Path):
        repository = repository.resolve()
        if not repository.is_dir():
            raise FileNotFoundError(f"Repository does not exist: {repository}")
        self.repository = repository
        self.path = repository / ".ai-team" / "state.sqlite3"
        self.json_path = repository / ".ai-team" / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute(
                    "CREATE TABLE IF NOT EXISTS run_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS lease (id INTEGER PRIMARY KEY CHECK(id=1), run_id TEXT NOT NULL, acquired_at TEXT NOT NULL)"
                )
                db.execute("PRAGMA user_version=3")
        except sqlite3.DatabaseError as exc:
            raise StateError(
                f"State database is corrupt or incompatible: {exc}"
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5, isolation_level="IMMEDIATE")

    def acquire(self, run_id: str) -> None:
        with self._connect() as db:
            row = db.execute("SELECT run_id FROM lease WHERE id=1").fetchone()
            if row and row[0] != run_id:
                state_row = db.execute(
                    "SELECT payload FROM run_state WHERE id=1"
                ).fetchone()
                try:
                    state = json.loads(state_row[0]) if state_row else None
                except json.JSONDecodeError as exc:
                    raise StateError(f"Persisted state is corrupt: {exc}") from exc
                if state and state.get("status") not in TERMINAL:
                    raise StateError(
                        f"Another active run holds the repository lease: {row[0]}"
                    )
                db.execute("DELETE FROM lease WHERE id=1")
            db.execute(
                "INSERT INTO lease(id,run_id,acquired_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET run_id=excluded.run_id, acquired_at=excluded.acquired_at",
                (run_id, datetime.now(UTC).isoformat()),
            )

    def release(self, run_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM lease WHERE id=1 AND run_id=?", (run_id,))

    def save(self, state: dict[str, Any]) -> None:
        state = _migrate_state(state)
        payload = json.dumps(state, ensure_ascii=False, default=str, sort_keys=True)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO run_state(id,payload,updated_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                    (payload, now),
                )
        except sqlite3.DatabaseError as exc:
            raise StateError(f"State transaction failed: {exc}") from exc
        self._atomic_json(state)

    def _atomic_json(self, state: dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(
            prefix="state-", suffix=".json.tmp", dir=self.json_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(state, handle, indent=2, ensure_ascii=False, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.json_path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def load(self) -> dict[str, Any] | None:
        try:
            with self._connect() as db:
                row = db.execute("SELECT payload FROM run_state WHERE id=1").fetchone()
            if not row:
                return None
            state = json.loads(row[0])
        except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
            raise StateError(f"Persisted state is corrupt: {exc}") from exc
        return _migrate_state(state)
