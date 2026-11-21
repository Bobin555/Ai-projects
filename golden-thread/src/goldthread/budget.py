"""Prices, spend ledger and budget guard."""
from __future__ import annotations

import sqlite3
from dataclasses import astuple, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

import yaml

from goldthread.config import HOSTED_PROVIDERS, Pack, PackError
from goldthread.core import Budget, Usage

PRICES_PATH = Path(__file__).with_name("prices.yaml")
MILLION = 1_000_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


class PriceTable:
    def __init__(self, prices: Mapping[str, Price]):
        self.prices = dict(prices)

    @classmethod
    def load(cls, path: Path = PRICES_PATH) -> "PriceTable":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls({model: Price(**p) for model, p in raw["usd_per_million_tokens"].items()})

    def get(self, model: str) -> Price | None:
        return self.prices.get(model)

    def most_expensive(self) -> Price:
        return max(self.prices.values(), key=lambda p: (p.output, p.input))


def worst_case_cost(price: Price, input_tokens: int, max_output_tokens: int) -> float:
    return (input_tokens * price.input + max_output_tokens * price.output) / MILLION


def actual_cost(price: Price, usage: Usage) -> float:
    return (usage.input_tokens * price.input + usage.output_tokens * price.output
            + usage.cache_read_input_tokens * price.cache_read
            + usage.cache_creation_input_tokens * price.cache_write) / MILLION


@dataclass(frozen=True)
class SpendEntry:
    run_id: str
    ts: str
    job: str
    model_requested: str
    served_by: str
    hosted: bool
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_write: int
    cost_usd: float
    price_assumed: bool
    fallback: bool
    duration_s: float


_COLUMNS = [f.name for f in fields(SpendEntry)]


class Ledger:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(f"CREATE TABLE IF NOT EXISTS spend ({', '.join(_COLUMNS)})")
        self.db.commit()

    def record(self, entry: SpendEntry) -> None:
        self.db.execute(f"INSERT INTO spend VALUES ({', '.join('?' for _ in _COLUMNS)})", astuple(entry))
        self.db.commit()

    def run_total(self, run_id: str) -> float:
        return self.db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM spend WHERE run_id = ?",
                               (run_id,)).fetchone()[0]

    def month_total(self, year_month: str) -> float:
        return self.db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM spend WHERE substr(ts, 1, 7) = ?",
                               (year_month,)).fetchone()[0]

    def last_run_id(self) -> str | None:
        row = self.db.execute("SELECT run_id FROM spend ORDER BY rowid DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def entries(self, run_id: str) -> list[SpendEntry]:
        rows = self.db.execute("SELECT * FROM spend WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
        return [_entry_from_row(r) for r in rows]


def _entry_from_row(row: tuple) -> SpendEntry:
    values = dict(zip(_COLUMNS, row))
    for name in ("hosted", "price_assumed", "fallback"):
        values[name] = bool(values[name])
    return SpendEntry(**values)


class BudgetExceeded(Exception):
    def __init__(self, limit: str, needed_usd: float, remaining_usd: float):
        super().__init__(f"budget: {limit} limit would be exceeded "
                         f"(needs up to ${needed_usd:.4f}, ${max(remaining_usd, 0):.4f} remaining)")
        self.limit = limit
        self.needed_usd = needed_usd
        self.remaining_usd = remaining_usd


class BudgetGuard:
    def __init__(self, budget: Budget, ledger: Ledger, prices: PriceTable, run_id: str,
                 now: Callable[[], datetime] = utc_now):
        self.budget, self.ledger, self.prices, self.run_id, self.now = budget, ledger, prices, run_id, now

    def check(self, job: str, model: str, hosted: bool, input_tokens: int, max_output_tokens: int) -> None:
        if not hosted:
            return
        price = self.prices.get(model) or self.prices.most_expensive()
        needed = worst_case_cost(price, input_tokens, max_output_tokens)
        run_spent = self.ledger.run_total(self.run_id)
        if run_spent + needed > self.budget.per_run_usd:
            raise BudgetExceeded("run", needed, self.budget.per_run_usd - run_spent)
        month_spent = self.ledger.month_total(self.now().strftime("%Y-%m"))
        if month_spent + needed > self.budget.per_month_usd:
            raise BudgetExceeded("month", needed, self.budget.per_month_usd - month_spent)

    def record(self, job: str, model_requested: str, served_by: str, hosted: bool, usage: Usage,
               fallback: bool, duration_s: float) -> SpendEntry:
        fallback = fallback or served_by != model_requested
        cost, assumed = 0.0, False
        if hosted:
            requested = self.prices.get(model_requested) or self.prices.most_expensive()
            served = self.prices.get(served_by)
            if served is None:
                served, assumed = self.prices.most_expensive(), True
            price = Price(*(max(a, b) for a, b in zip(astuple(requested), astuple(served))))
            cost = actual_cost(price, usage)
        entry = SpendEntry(self.run_id, self.now().strftime("%Y-%m-%dT%H:%M:%SZ"), job, model_requested,
                           served_by, hosted, usage.input_tokens, usage.output_tokens,
                           usage.cache_read_input_tokens, usage.cache_creation_input_tokens,
                           cost, assumed, fallback, duration_s)
        self.ledger.record(entry)
        return entry


def validate_prices(pack: Pack, prices: PriceTable) -> None:
    for spec in pack.models.values():
        if spec.provider in HOSTED_PROVIDERS and prices.get(spec.model) is None:
            raise PackError(f"no price for model '{spec.model}'")


@dataclass(frozen=True)
class RunCostSummary:
    run_id: str
    per_job_model: dict[tuple[str, str], tuple[int, int, float]]
    run_usd: float
    month_usd: float
    month_remaining_usd: float


def summarise(ledger: Ledger, budget: Budget, run_id: str, now: Callable[[], datetime] = utc_now) -> RunCostSummary:
    totals: dict[tuple[str, str], tuple[int, int, float]] = {}
    for e in ledger.entries(run_id):
        i, o, c = totals.get((e.job, e.served_by), (0, 0, 0.0))
        totals[(e.job, e.served_by)] = (i + e.input_tokens, o + e.output_tokens, c + e.cost_usd)
    month = ledger.month_total(now().strftime("%Y-%m"))
    return RunCostSummary(run_id, totals, ledger.run_total(run_id), month, budget.per_month_usd - month)


def render_cost_summary(s: RunCostSummary) -> str:
    lines = [f"Cost summary for run {s.run_id}"]
    for (job, model), (i, o, c) in sorted(s.per_job_model.items()):
        lines.append(f"  {job} · {model}: {i:,} input / {o:,} output tokens, ${c:.4f}")
    if not s.per_job_model:
        lines.append("  no model calls")
    lines.append(f"This run: ${s.run_usd:.4f} · This month: ${s.month_usd:.2f} · "
                 f"Month budget remaining: ${s.month_remaining_usd:.2f}")
    return "\n".join(lines)
