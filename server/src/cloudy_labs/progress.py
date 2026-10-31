"""Lab progress in a local SQLite file: attempts and the results of each check run."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .checks import CheckResult

# Bump with a new entry in MIGRATIONS; never edit an applied one.
MIGRATIONS = [
    """
    CREATE TABLE attempts (
        id INTEGER PRIMARY KEY,
        lab_id TEXT NOT NULL,
        started_at TEXT NOT NULL
    );
    CREATE TABLE check_runs (
        attempt_id INTEGER NOT NULL REFERENCES attempts(id),
        check_id TEXT NOT NULL,
        passed INTEGER NOT NULL,
        message TEXT NOT NULL,
        resource_ids_json TEXT NOT NULL,
        ran_at TEXT NOT NULL
    );
    CREATE INDEX check_runs_attempt ON check_runs(attempt_id, ran_at);
    """,
]


@dataclass(frozen=True)
class Attempt:
    id: int
    lab_id: str
    started_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Progress:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
            self.db.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {i};\nCOMMIT;")

    def close(self) -> None:
        self.db.close()

    def start_attempt(self, lab_id: str) -> Attempt:
        with self.db:
            cur = self.db.execute("INSERT INTO attempts (lab_id, started_at) VALUES (?, ?)", (lab_id, _now()))
        return self._attempt("WHERE id = ?", (cur.lastrowid,))  # type: ignore[return-value]

    def current_attempt(self) -> Attempt | None:
        """The most recent attempt at any lab: the emulator state belongs to it."""
        return self._attempt("", ())

    def latest_attempt(self, lab_id: str) -> Attempt | None:
        return self._attempt("WHERE lab_id = ?", (lab_id,))

    def _attempt(self, where: str, params: tuple) -> Attempt | None:
        row = self.db.execute(f"SELECT * FROM attempts {where} ORDER BY id DESC LIMIT 1", params).fetchone()
        return Attempt(row["id"], row["lab_id"], row["started_at"]) if row else None

    def record_checks(self, attempt_id: int, results: list[CheckResult]) -> None:
        ran_at = _now()  # one timestamp per run groups its rows
        with self.db:
            self.db.executemany(
                "INSERT INTO check_runs VALUES (?, ?, ?, ?, ?, ?)",
                [(attempt_id, r.check_id, r.passed, r.message, json.dumps(r.resource_ids), ran_at) for r in results],
            )

    def record_if_changed(self, attempt_id: int, results: list[CheckResult]) -> bool:
        """Record a run only when it differs from the attempt's last one, so the lab-server's
        automatic runs do not fill the history with repeats. Whether it recorded."""
        if self._results(attempt_id) == results:
            return False
        self.record_checks(attempt_id, results)
        return True

    def latest_results(self, lab_id: str) -> list[CheckResult]:
        """Results of the last check run in the lab's latest attempt."""
        attempt = self.latest_attempt(lab_id)
        return self._results(attempt.id) if attempt else []

    def _results(self, attempt_id: int) -> list[CheckResult]:
        rows = self.db.execute(
            """SELECT * FROM check_runs WHERE attempt_id = ?
               AND ran_at = (SELECT MAX(ran_at) FROM check_runs WHERE attempt_id = ?)
               ORDER BY rowid""",
            (attempt_id, attempt_id),
        ).fetchall()
        return [
            CheckResult(bool(r["passed"]), r["message"], json.loads(r["resource_ids_json"]), r["check_id"])
            for r in rows
        ]

    def lab_summary(self) -> dict[str, bool]:
        """lab id -> whether any check run of any attempt passed every check."""
        rows = self.db.execute(
            """SELECT a.lab_id, MAX(run_ok) AS done FROM (
                   SELECT attempt_id, ran_at, MIN(passed) AS run_ok FROM check_runs GROUP BY attempt_id, ran_at
               ) r JOIN attempts a ON a.id = r.attempt_id GROUP BY a.lab_id"""
        ).fetchall()
        return {r["lab_id"]: bool(r["done"]) for r in rows}
