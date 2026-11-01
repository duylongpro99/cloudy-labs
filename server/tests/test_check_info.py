"""Info check results: shown to the learner, never graded."""

import sqlite3
from datetime import datetime, timezone

from cloudy_labs import reachability
from cloudy_labs.graph.collector import emulator_down
from cloudy_labs.checks import CheckContext, CheckResult, reachability_result
from cloudy_labs.progress import MIGRATIONS, Progress
from cloudy_labs.reachability.model import Hop, Reachability


def test_info_results_do_not_block_completion(tmp_path):
    p = Progress(tmp_path / "progress.db")
    a = p.start_attempt("lab-x")
    p.record_checks(a.id, [CheckResult(True, "ok", [], "c1"), CheckResult(False, "blocked", ["sg-1"], "c2", info=True)])
    assert p.lab_summary() == {"lab-x": True}
    assert [r.info for r in p.latest_results("lab-x")] == [False, True]


def test_a_failed_graded_check_still_blocks(tmp_path):
    p = Progress(tmp_path / "progress.db")
    a = p.start_attempt("lab-x")
    p.record_checks(a.id, [CheckResult(False, "no", [], "c1"), CheckResult(True, "ok", [], "c2", info=True)])
    assert p.lab_summary() == {"lab-x": False}


def test_an_existing_database_gains_the_column_and_a_backup(tmp_path):
    path = tmp_path / "progress.db"
    db = sqlite3.connect(path)
    db.executescript(f"BEGIN;\n{MIGRATIONS[0]}\nPRAGMA user_version = 1;\nCOMMIT;")
    db.execute("INSERT INTO attempts VALUES (1, 'lab-x', '2026-10-31')")
    db.execute("INSERT INTO check_runs VALUES (1, 'c1', 1, 'ok', '[]', '2026-10-31')")
    db.commit()
    db.close()
    p = Progress(path)
    assert [(r.passed, r.info) for r in p.latest_results("lab-x")] == [(True, False)]
    assert (tmp_path / "progress.db.v1.bak").is_file()


def _found(ok):
    hops = [Hop("internet", "internet", "forward", "routed"), Hop("sg-1", "security-group", "deny" if not ok else "allow",
                                                                   "no-matching-rule" if not ok else "allowed")]
    return Reachability(ok, hops, None if ok else "sg-1", "delivered" if ok else "no-matching-rule")


def test_reachability_result_is_info_until_grading_is_enabled(monkeypatch):
    monkeypatch.setattr(reachability, "GRADING_ENABLED", False)
    r = reachability_result(_found(False), "web reachable")
    assert (r.passed, r.info, r.resource_ids) == (False, True, ["sg-1"])
    assert "blocked at sg-1: no-matching-rule" in r.message and "[analysed]" in r.message
    monkeypatch.setattr(reachability, "GRADING_ENABLED", True)
    assert reachability_result(_found(True), "web reachable").info is False
    assert reachability_result(_found(True), "db private", expect=False).passed is False


def test_reachable_uses_the_given_collect(monkeypatch):
    seen = []

    def collect(kinds):
        seen.append(tuple(kinds))
        return emulator_down(datetime(2026, 10, 31, tzinfo=timezone.utc))

    ctx = CheckContext(client=lambda s: None, collect=collect)
    found = ctx.reachable("internet", "198.51.100.1", 443)
    assert seen == [reachability.NETWORK_KINDS]
    assert found.label == "analysed"
