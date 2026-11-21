"""Regression tests from the final review: incomplete answers (I3), short unsourced claims (M3), fallback costs (I4),
budget stop in ask (M1), audit detail (M4), evaluation metric, served_by and resume check (M5)."""
import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import goldthread.cli as cli
from goldthread.aliases import AliasTable
from goldthread.answerer import ask
from goldthread.audit import AuditLog
from goldthread.budget import BudgetExceeded, BudgetGuard, Ledger, Price, PriceTable
from goldthread.config import load_pack, pack_version
from goldthread.core import Budget, ModelSpec, Usage
from goldthread.evaluate import render_eval_report_md, run_eval
from goldthread.extractor import extract_pack
from goldthread.models.base import Prompt, RawAnswer, RawBlock, RawCitation
from goldthread.models.claude import ClaudeConnector
from goldthread.models.fake import FakeConnector
from goldthread.render import render_answer_html, render_answer_md

Q = "What is the fuel temperature limit?"


@pytest.fixture
def env(synthetic_pack, store, tmp_path):
    return dict(pack=synthetic_pack, store=store, aliases=AliasTable.from_csv(synthetic_pack.aliases_path),
                ledger=Ledger(tmp_path / "ledger.sqlite3"), audit=AuditLog(tmp_path / "audit.jsonl"), tmp=tmp_path)


def run(env, connector, question=Q, guard=None):
    pack = env["pack"]
    guard = guard or BudgetGuard(pack.budget, env["ledger"], PriceTable.load(), "run-1")
    return ask(pack, env["store"], env["aliases"], connector, pack.models["answer"], guard, env["audit"], question,
               run_id="run-1")


def raw(blocks, stop):
    return RawAnswer(tuple(blocks), stop, "fake", False, Usage(10, 10))


# --- I3: an answer cut short is never "not found" -------------------------------------------------------------

def test_truncated_answer_is_incomplete_not_not_found(env):
    ans = run(env, FakeConnector(script={Q: raw([RawBlock("The fuel temperature limit is", ())], "max_tokens")}))
    assert ans.kind == "incomplete" and [s.text for s in ans.statements] == ["The fuel temperature limit is"]
    md = render_answer_md(ans)
    assert "⚠ Incomplete answer" in md and "max_tokens" in md and "Not found" not in md
    assert "The fuel temperature limit is" in md and "Incomplete answer" in render_answer_html(ans)


@pytest.mark.parametrize("stop", ["max_tokens", "end_turn"])
def test_empty_reply_is_incomplete_not_not_found(env, stop):
    ans = run(env, FakeConnector(script={Q: raw([], stop)}))
    assert ans.kind == "incomplete" and ans.statements == ()
    assert 'not a "not found" result' in render_answer_md(ans)


@pytest.mark.parametrize("text", ["NOT_FOUND.", "not found", "**NOT_FOUND**", "NOT FOUND\n"])
def test_not_found_sentinel_variants(env, text):
    assert run(env, FakeConnector(script={Q: [RawBlock(text, ())]})).kind == "not_found"


def test_sentence_containing_not_found_is_an_answer(env):  # control: the sentinel match is the whole reply only
    assert run(env, FakeConnector(script={Q: [RawBlock("The defect was not found in any pebble.", ())]})).kind == "answer"


def cli_run(pack, tmp_path, capsys, *args):
    code = cli.main(["--pack", str(pack.root), "--data-root", str(tmp_path / "data"), *args])
    out, err = capsys.readouterr()
    return code, out, err


def test_cli_ask_incomplete_exits_1(synthetic_pack, tmp_path, capsys, monkeypatch):
    cli_run(synthetic_pack, tmp_path, capsys, "ingest")
    conn = FakeConnector(script={Q: raw([RawBlock("The fuel temperature limit is", ())], "max_tokens")})
    monkeypatch.setattr(cli, "get_connector", lambda provider, pack=None, client=None: conn)
    code, out, _ = cli_run(synthetic_pack, tmp_path, capsys, "ask", Q)
    assert code == 1 and "Incomplete answer" in out


# --- M3: a short factual sentence without a source is flagged ------------------------------------------------

def test_short_factual_sentence_is_unsourced(env):
    blocks = [RawBlock("Based on the results:", ()), RawBlock("The limit is 1700 C.", ()), RawBlock("It is acceptable.", ())]
    ans = run(env, FakeConnector(script={Q: blocks}))
    assert [s.status for s in ans.statements] == ["connective", "unsourced", "unsourced"]


# --- M1: a budget stop in ask is a clean exit 3 ----------------------------------------------------------------

def test_cli_ask_budget_stop_exits_3(synthetic_pack, tmp_path, capsys, monkeypatch):
    cli_run(synthetic_pack, tmp_path, capsys, "ingest")

    def stop(*a, **k):
        raise BudgetExceeded("run", 0.5, 0.1)

    monkeypatch.setattr(cli, "ask", stop)
    code, out, err = cli_run(synthetic_pack, tmp_path, capsys, "ask", Q)
    assert code == 3 and "run limit would be exceeded" in err and "Raise the limit in pack.yaml" in err


# --- M4: the audit line records what was answered, from which pack ---------------------------------------------

def test_audit_line_has_pack_version_provider_and_statements(env):
    run(env, FakeConnector())
    event = json.loads((env["tmp"] / "audit.jsonl").read_text().splitlines()[-1])
    assert event["pack_version"] == pack_version(env["pack"]) and event["provider"] == "fake"
    assert event["stop_reason"] == "end_turn"
    first = event["statements"][0]
    assert first["status"] == "verified" and first["text"]
    assert first["citations"][0]["address"] and first["citations"][0]["quote"] and first["citations"][0]["ok"] is True


# --- I4: every attempt of a fallback is priced, and the pre-check reserves for it ---------------------------------

def iteration(kind, model, i, o):
    return NS(type=kind, model=model, input_tokens=i, output_tokens=o, cache_read_input_tokens=0,
              cache_creation_input_tokens=None)


def test_claude_connector_parses_usage_iterations():
    usage = NS(input_tokens=100, output_tokens=50, cache_read_input_tokens=0, cache_creation_input_tokens=0,
               iterations=[iteration("message", None, 100, 0), iteration("fallback_message", "claude-opus-4-8", 100, 50)])
    resp = NS(content=[NS(type="fallback"), NS(type="text", text="ok", citations=None)], model="claude-opus-4-8",
              stop_reason="end_turn", usage=usage)
    conn = ClaudeConnector(NS(beta=NS(messages=NS(create=lambda **kw: resp))))
    spec = ModelSpec("claude", "claude-opus-5-5", "high", 16000)
    expected = (("claude-opus-5-5", Usage(100, 0, 0, 0)), ("claude-opus-4-8", Usage(100, 50, 0, 0)))
    assert conn.answer(spec, Prompt("S", "Q")).iterations == expected
    assert conn.structured(spec, Prompt("S", "Q", schema={"type": "object"})).iterations == expected
    assert conn.fallback is True and FakeConnector().fallback is False


def guard_for(tmp_path, budget=Budget(100, 100)):
    prices = PriceTable({"claude-opus-5-5": Price(4, 20, 0.2, 5), "claude-opus-4-8": Price(5, 25, 0.5, 6.25)})
    return BudgetGuard(budget, Ledger(tmp_path / "l.sqlite3"), prices, "run-1")


def test_guard_record_prices_each_attempt(tmp_path):
    entry = guard_for(tmp_path).record(
        "answer", "claude-opus-5-5", "claude-opus-4-8", True, Usage(1_000_000, 1_000_000), True, 1.0,
        iterations=(("claude-opus-5-5", Usage(1_000_000, 0)), ("claude-opus-4-8", Usage(1_000_000, 1_000_000))))
    assert entry.cost_usd == pytest.approx(4 + 5 + 25) and entry.price_assumed is False
    assert (entry.input_tokens, entry.output_tokens) == (2_000_000, 1_000_000)


def test_guard_record_unknown_attempt_model_is_assumed(tmp_path):
    entry = guard_for(tmp_path).record("answer", "claude-opus-5-5", "claude-mystery", True, Usage(1_000_000, 0), True,
                                       1.0, iterations=(("claude-mystery", Usage(1_000_000, 0)),))
    assert entry.cost_usd == pytest.approx(5) and entry.price_assumed is True


def test_guard_check_reserves_fallback_worst_case(tmp_path):
    guard = guard_for(tmp_path, Budget(6, 100))
    guard.check("answer", "claude-opus-5-5", True, 1_000_000, 0)  # $4 fits in $6
    with pytest.raises(BudgetExceeded) as exc:
        guard.check("answer", "claude-opus-5-5", True, 1_000_000, 0, fallback=True)  # $4 + up to $5 more does not
    assert exc.value.needed_usd == pytest.approx(9)


ITER = (("fake", Usage(5, 5)),)


class FallbackFake(FakeConnector):
    fallback = True

    def answer(self, spec, prompt):
        return replace(super().answer(spec, prompt), iterations=ITER)

    def structured(self, spec, prompt):
        return replace(super().structured(spec, prompt), iterations=ITER)


class RecordingGuard(BudgetGuard):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.checks, self.records = [], []

    def check(self, *a, fallback=False, **k):
        self.checks.append(fallback)
        return super().check(*a, fallback=fallback, **k)

    def record(self, *a, iterations=(), **k):
        self.records.append(iterations)
        return super().record(*a, iterations=iterations, **k)


def test_callers_pass_fallback_and_iterations(env):
    pack = env["pack"]
    guard = RecordingGuard(pack.budget, env["ledger"], PriceTable.load(), "run-1")
    run(env, FallbackFake(), guard=guard)
    extract_pack(pack, env["store"], FallbackFake(), pack.models["extract"], guard, env["audit"], "run-1",
                 only_docs=["SYN-SE"])
    run_eval(pack, env["store"], env["aliases"], {"answer": FallbackFake(), "judge": FallbackFake()}, guard,
             env["audit"], "run-1")
    assert len(guard.checks) >= 4 and all(guard.checks)
    assert guard.records == [ITER] * len(guard.checks)


# --- M5: evaluation reports the verified-quote rate and who served each question; resume needs the same pack -------

def test_eval_reports_quotes_verified_rate_and_served_by(env):
    addr = "SYN-SAR@r2#p1.2"
    q1 = env["pack"].tests[0].question
    blocks = [RawBlock("The fuel temperature limit is 1650 C.", (RawCitation(addr, "The fuel temperature limit is 1650 C."),)),
              RawBlock("It was 1700 C.", (RawCitation(addr, "It was 1700 C."),))]
    guard = BudgetGuard(Budget(100, 100), env["ledger"], PriceTable.load(), "eval-q")
    report = run_eval(env["pack"], env["store"], env["aliases"],
                      {"answer": FakeConnector(script={q1: blocks}), "judge": FakeConnector()}, guard, env["audit"],
                      "eval-q")
    approved = [r for r in report.results if r.status == "approved"]
    rate = sum(r.quotes_verified for r in approved) / sum(r.quotes_total for r in approved)
    assert rate < 1 and report.metrics["quotes_verified_rate"] == pytest.approx(rate)
    assert all(r.served_by == "fake" for r in report.results if r.answer_kind == "answer")
    assert "served by" in render_eval_report_md(report)


def test_eval_resume_refuses_a_changed_pack(env):
    pack = env["pack"]
    connectors = {"answer": FakeConnector(), "judge": FakeConnector()}
    guard = BudgetGuard(Budget(100, 100), env["ledger"], PriceTable.load(), "eval-r")
    run_eval(pack, env["store"], env["aliases"], connectors, guard, env["audit"], "eval-r")
    (pack.root / "rules.md").write_text("Changed rules.\n", encoding="utf-8")
    changed = load_pack(pack.root, data_root=pack.data_dir.parent)
    with pytest.raises(ValueError, match="pack version"):
        run_eval(changed, env["store"], env["aliases"], connectors, guard, env["audit"], "eval-r", resume=True)
