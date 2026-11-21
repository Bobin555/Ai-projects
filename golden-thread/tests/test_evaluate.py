import json

import pytest

from goldthread.aliases import AliasTable
from goldthread.audit import AuditLog
from goldthread.budget import BudgetGuard, Ledger, Price, PriceTable
from goldthread.config import pack_version
from goldthread.core import Budget
from goldthread.evaluate import SUCCESS_THRESHOLDS, render_eval_report_md, run_eval, write_eval_report
from goldthread.models.fake import FakeConnector


@pytest.fixture
def env(synthetic_pack, store, tmp_path):
    return dict(pack=synthetic_pack, store=store, aliases=AliasTable.from_csv(synthetic_pack.aliases_path),
                ledger=Ledger(tmp_path / "ledger.sqlite3"), audit=AuditLog(tmp_path / "audit.jsonl"))


def evaluate(env, answer=None, guard=None, run_id="eval-1", resume=False):
    pack = env["pack"]
    guard = guard or BudgetGuard(pack.budget, env["ledger"], PriceTable.load(), run_id)
    connectors = {"answer": answer or FakeConnector(), "judge": FakeConnector()}
    return run_eval(pack, env["store"], env["aliases"], connectors, guard, env["audit"], run_id, resume=resume)


def test_thresholds():
    assert SUCCESS_THRESHOLDS == {"retrieval_hit_rate": 0.80, "not_found_accuracy": 1.0, "verified_quote_integrity": 1.0}


def test_eval_metrics_on_synthetic(env):
    report = evaluate(env)
    assert report.metrics["retrieval_hit_rate"] == 1.0
    assert report.metrics["not_found_accuracy"] == 1.0
    assert report.metrics["verified_quote_integrity"] == 1.0
    assert report.passed is True and report.stopped is None
    by_id = {r.id: r for r in report.results}
    assert by_id["q4"].status == "draft" and set(by_id) == {"q1", "q2", "q3", "q4"}
    assert by_id["q1"].judge == "yes" and by_id["q3"].judge == "yes" and by_id["q2"].answer_kind == "not_found"
    assert by_id["q2"].retrieval_hit is None and by_id["q1"].expected_cited is True


def test_drafts_do_not_count(env):
    q4 = env["pack"].tests[3].question
    report = evaluate(env, answer=FakeConnector(script={q4: "NOT_FOUND"}))  # q4 is a draft that now fails
    assert report.passed is True and next(r for r in report.results if r.id == "q4").not_found_ok is False


def test_eval_fails_threshold(env):
    q1 = env["pack"].tests[0].question
    report = evaluate(env, answer=FakeConnector(script={q1: "NOT_FOUND"}))
    assert report.metrics["not_found_accuracy"] < 1.0 and report.passed is False


def test_reports_written_with_versions(env):
    report = evaluate(env)
    md_path, json_path = write_eval_report(env["pack"], report)
    md = md_path.read_text()
    assert md_path.parent == env["pack"].data_dir / "reports" and md_path.name == "eval-eval-1.md"
    assert pack_version(env["pack"]) in md and "answer=fake" in md and "PASSED" in md
    assert json.loads(json_path.read_text())["results"][0]["id"] == "q1"
    assert render_eval_report_md(report) == md


def test_eval_budget_stop_and_resume(env):
    pricey = PriceTable({"fake": Price(1000, 0, 0, 0)})
    hosted = FakeConnector(hosted=True)
    tight = BudgetGuard(Budget(0.5, 100), env["ledger"], pricey, "eval-b")
    first = evaluate(env, answer=hosted, guard=tight, run_id="eval-b")
    assert first.stopped == "budget: run limit" and first.remaining and first.passed is False
    done_first = {r.id for r in first.results}
    roomy = BudgetGuard(Budget(100, 100), env["ledger"], pricey, "eval-b")
    second = evaluate(env, answer=hosted, guard=roomy, run_id="eval-b", resume=True)
    assert second.stopped is None and second.remaining == []
    assert [r.id for r in second.results] == ["q1", "q2", "q3", "q4"] and done_first < {r.id for r in second.results}
