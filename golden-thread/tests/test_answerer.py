import json

import pytest

from goldthread.aliases import AliasTable
from goldthread.answerer import Answer, Statement, ask
from goldthread.audit import AuditLog
from goldthread.budget import BudgetExceeded, BudgetGuard, Ledger, Price, PriceTable
from goldthread.core import Budget
from goldthread.models.base import RawBlock, RawCitation
from goldthread.models.fake import FakeConnector
from goldthread.render import render_answer_html, render_answer_md

Q = "What is the fuel temperature limit?"


class Spy(FakeConnector):
    calls = 0

    def answer(self, spec, prompt):
        type(self).calls += 1
        return super().answer(spec, prompt)


@pytest.fixture
def env(synthetic_pack, store, tmp_path):
    aliases = AliasTable.from_csv(synthetic_pack.aliases_path)
    guard = BudgetGuard(synthetic_pack.budget, Ledger(tmp_path / "ledger.sqlite3"), PriceTable.load(), "run-1")
    audit = AuditLog(tmp_path / "audit.jsonl")
    return synthetic_pack, store, aliases, guard, audit


def run(env, question, connector=None, guard=None):
    pack, store, aliases, default_guard, audit = env
    return ask(pack, store, aliases, connector or FakeConnector(), pack.models["answer"],
               guard or default_guard, audit, question, run_id="run-1")


def addr(store, needle):
    return next(p.address for d in store.documents() for p in store.passages_of(d.doc_id, d.revision)
                if needle in p.text)


def test_answer_verified_statements(env):
    ans = run(env, Q)
    assert ans.kind == "answer" and ans.statements
    assert all(s.status == "verified" for s in ans.statements)
    issued = {d.key for d in env[1].documents(status="issued")}
    assert all(c.address.split("#")[0] in issued for s in ans.statements for c in s.citations)


def test_no_hits_not_found_without_model_call(env):
    Spy.calls = 0
    ans = run(env, "zzzz qqqq", connector=Spy())
    assert ans.kind == "not_found" and Spy.calls == 0 and ans.cost_usd == 0
    assert any(s.startswith("SYN-SAR@r2 — ") for s in ans.searched)
    assert not any("@r1 — Synthetic Safety Analysis" in s for s in ans.searched)


def test_model_not_found_sentinel(env):
    ans = run(env, Q, connector=FakeConnector(script={Q: "NOT_FOUND"}))
    assert ans.kind == "not_found" and len(ans.searched) == 3
    assert "Not found. Searched:" in render_answer_md(ans)


def test_flagged_quote_shown_with_reason(env):
    a = addr(env[1], "1650 C")
    bad = [RawBlock("The limit is 1700 C.", (RawCitation(a, "The fuel temperature limit is 1700 C."),))]
    ans = run(env, Q, connector=FakeConnector(script={Q: bad}))
    assert ans.statements[0].status == "flagged"
    assert ans.statements[0].citations[0].reason == "quote not found in passage"
    assert "⚠" in render_answer_md(ans)


def test_unsourced_and_connective(env):
    blocks = [RawBlock("Based on the results:", ()),
              RawBlock("The limit was raised in a later revision of the report.", ())]
    ans = run(env, Q, connector=FakeConnector(script={Q: blocks}))
    assert [s.status for s in ans.statements] == ["connective", "unsourced"]
    assert "⚠ no source:" in render_answer_md(ans)


def test_refusal_is_not_not_found(env):  # Review Focus 5
    ans = run(env, Q, connector=FakeConnector(script={Q: "REFUSE"}))
    assert ans.kind == "refused"
    assert 'not a "not found" result' in render_answer_md(ans)


def test_budget_stop_raises_before_call(env, tmp_path):
    Spy.calls = 0
    guard = BudgetGuard(Budget(0.01, 0.01), Ledger(tmp_path / "l2.sqlite3"),
                        PriceTable({"fake": Price(1000, 1000, 0, 0)}), "run-1")
    with pytest.raises(BudgetExceeded):
        run(env, Q, connector=Spy(hosted=True), guard=guard)
    assert Spy.calls == 0


def test_audit_line_written(env, tmp_path):
    run(env, Q)
    event = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[-1])
    assert event["event"] == "ask" and event["kind"] == "answer" and event["hits"]
    assert event["question"] == Q and "ts" in event


def test_render_verified_shows_address_and_quote(env):
    ans = run(env, Q)
    md = render_answer_md(ans)
    c = ans.statements[0].citations[0]
    assert f"`{c.address}`" in md and c.quote in md


def test_render_not_found_with_outside(env):
    ans = Answer("q", "not_found", (), ("A@r1 — Doc A",), (), "fake", "", "run-1", 0.0)
    md = render_answer_md(ans, outside="Evidence documents")
    assert "Not found. Searched:" in md and "A@r1 — Doc A" in md
    assert "Outside this corpus:" in md and "Evidence documents" in md


def test_render_html_escapes():
    ans = Answer("q", "answer", (Statement("<b>bold</b> claim that is long enough", (), "unsourced"),),
                 (), (), "fake", "fake", "run-1", 0.0)
    html = render_answer_html(ans)
    assert "&lt;b&gt;" in html and "<b>bold" not in html
