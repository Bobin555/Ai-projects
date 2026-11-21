from datetime import datetime, timezone

import pytest

from goldthread.budget import (
    BudgetExceeded, BudgetGuard, Ledger, Price, PriceTable, SpendEntry, actual_cost,
    render_cost_summary, summarise, validate_prices, worst_case_cost,
)
from goldthread.config import PackError, load_pack
from goldthread.core import Budget, Usage

NOV = lambda: datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)  # noqa: E731
OPUS55 = Price(4.00, 20.00, 0.20, 5.00)


def entry(run_id, cost, ts="2026-11-21T10:00:00Z", **kw):
    base = dict(run_id=run_id, ts=ts, job="extract", model_requested="claude-opus-5-5",
                served_by="claude-opus-5-5", hosted=True, input_tokens=10, output_tokens=5,
                cache_read=0, cache_write=0, cost_usd=cost, price_assumed=False, fallback=False, duration_s=1.0)
    base.update(kw)
    return SpendEntry(**base)


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.sqlite3")


@pytest.fixture
def prices():
    return PriceTable.load()


def test_price_table_values(prices):
    assert prices.get("claude-opus-5-5") == OPUS55
    assert prices.get("claude-sonnet-5-5") == Price(2.00, 10.00, 0.10, 2.50)
    assert prices.get("nope") is None
    assert prices.most_expensive().output == 25.00


def test_worst_case_cost():
    assert worst_case_cost(OPUS55, 100_000, 16_000) == pytest.approx(0.72)


def test_actual_cost_with_cache():
    assert actual_cost(OPUS55, Usage(1000, 500, 2000, 1000)) == pytest.approx(0.0194)


def test_guard_stops_before_run_limit(ledger, prices):
    ledger.record(entry("run-a", 0.5))
    guard = BudgetGuard(Budget(1.0, 100), ledger, prices, "run-a", now=NOV)
    with pytest.raises(BudgetExceeded) as exc:
        guard.check("extract", "claude-opus-5-5", True, 100_000, 16_000)
    assert exc.value.limit == "run"
    assert exc.value.remaining_usd == pytest.approx(0.5)
    assert exc.value.needed_usd == pytest.approx(0.72)


def test_guard_allows_within_limits(ledger, prices):
    BudgetGuard(Budget(1.0, 100), ledger, prices, "run-a", now=NOV).check("extract", "claude-opus-5-5", True, 1000, 1000)


def test_guard_month_limit_spans_runs(ledger, prices):
    ledger.record(entry("run-a", 0.6))
    guard = BudgetGuard(Budget(10.0, 1.0), ledger, prices, "run-b", now=NOV)
    with pytest.raises(BudgetExceeded) as exc:
        guard.check("answer", "claude-opus-5-5", True, 100_000, 16_000)
    assert exc.value.limit == "month" and exc.value.remaining_usd == pytest.approx(0.4)


def test_month_boundary(ledger):
    ledger.record(entry("run-a", 0.3, ts="2026-10-31T23:59:59Z"))
    ledger.record(entry("run-b", 0.2, ts="2026-11-01T00:00:00Z"))
    assert ledger.month_total("2026-11") == pytest.approx(0.2)
    assert ledger.month_total("2026-10") == pytest.approx(0.3)


def test_unknown_served_model_priced_conservatively(ledger, prices):  # Review Focus 5
    guard = BudgetGuard(Budget(10, 100), ledger, prices, "run-a", now=NOV)
    e = guard.record("answer", "claude-opus-5-5", "claude-mystery", True, Usage(1000, 1000), False, 2.0)
    assert e.cost_usd == pytest.approx(actual_cost(prices.most_expensive(), Usage(1000, 1000)))
    assert e.price_assumed is True and e.fallback is True


def test_fallback_uses_max_price(ledger, prices):
    guard = BudgetGuard(Budget(10, 100), ledger, prices, "run-a", now=NOV)
    e = guard.record("answer", "claude-sonnet-5-5", "claude-opus-4-8", True, Usage(1000, 1000), True, 2.0)
    assert e.cost_usd == pytest.approx(actual_cost(prices.get("claude-opus-4-8"), Usage(1000, 1000)))
    assert e.price_assumed is False


def test_local_costs_zero_records_tokens(ledger, prices):
    guard = BudgetGuard(Budget(0.0, 0.0), ledger, prices, "run-a", now=NOV)
    guard.check("extract", "fake", False, 10_000_000, 10_000)  # free, never blocked
    e = guard.record("extract", "fake", "fake", False, Usage(123, 45), False, 3.5)
    assert e.cost_usd == 0 and ledger.entries("run-a") == [e]
    assert (e.input_tokens, e.output_tokens, e.duration_s) == (123, 45, 3.5)


def test_validate_prices_rejects_unknown_hosted_model(synthetic_pack_dir, prices):
    p = synthetic_pack_dir / "pack.yaml"
    p.write_text(p.read_text().replace("offline: true", "offline: false").replace(
        "extract: {provider: fake, model: fake", "extract: {provider: claude, model: claude-unknown"))
    with pytest.raises(PackError, match="no price for model 'claude-unknown'"):
        validate_prices(load_pack(synthetic_pack_dir), prices)


def test_summary_and_render(ledger, prices):
    guard = BudgetGuard(Budget(20, 150), ledger, prices, "run-a", now=NOV)
    guard.record("extract", "claude-opus-5-5", "claude-opus-5-5", True, Usage(1000, 500, 2000, 1000), False, 1.0)
    guard.record("extract", "claude-opus-5-5", "claude-opus-5-5", True, Usage(1000, 500, 2000, 1000), False, 1.0)
    s = summarise(ledger, Budget(20, 150), "run-a", now=NOV)
    assert s.per_job_model[("extract", "claude-opus-5-5")] == (2000, 1000, pytest.approx(0.0388))
    assert s.run_usd == pytest.approx(0.0388) and s.month_remaining_usd == pytest.approx(150 - 0.0388)
    text = render_cost_summary(s)
    assert "extract" in text and "claude-opus-5-5" in text
    assert f"${s.run_usd:.4f}" in text and f"${s.month_remaining_usd:.2f}" in text
