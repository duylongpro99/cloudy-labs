import sqlite3

from cloudy_labs.checks import CheckResult
from cloudy_labs.progress import MIGRATIONS, Progress


def test_fresh_db_is_migrated_and_survives_reopen(tmp_path):
    path = tmp_path / "nested" / "progress.db"
    p = Progress(path)
    a = p.start_attempt("lab-a")
    p.close()
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    p = Progress(path)  # reopening must not rerun migrations
    assert p.current_attempt() == a


def test_attempts_and_latest_results(tmp_path):
    p = Progress(tmp_path / "p.db")
    assert p.current_attempt() is None and p.latest_results("lab-a") == []
    a1 = p.start_attempt("lab-a")
    p.record_checks(a1.id, [CheckResult(False, "no vpc", [], "vpc"), CheckResult(True, "ok", ["sg-1"], "sg")])
    p.record_checks(a1.id, [CheckResult(True, "vpc ok", ["vpc-1"], "vpc"), CheckResult(True, "ok", ["sg-1"], "sg")])
    b = p.start_attempt("lab-b")
    assert p.current_attempt() == b
    assert p.latest_attempt("lab-a") == a1
    assert p.latest_results("lab-a") == [
        CheckResult(True, "vpc ok", ["vpc-1"], "vpc"),
        CheckResult(True, "ok", ["sg-1"], "sg"),
    ]
    assert p.latest_results("lab-b") == []
    p.record_checks(b.id, [CheckResult(False, "missing", [], "x")])
    assert p.lab_summary() == {"lab-a": True, "lab-b": False}


def test_completed_stays_true_after_a_new_attempt(tmp_path):
    p = Progress(tmp_path / "p.db")
    a = p.start_attempt("lab-a")
    p.record_checks(a.id, [CheckResult(True, "ok", [], "c")])
    p.start_attempt("lab-a")
    assert p.lab_summary() == {"lab-a": True}
    assert p.latest_results("lab-a") == []
