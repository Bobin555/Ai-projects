"""Run a pack's test questions and score them."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

from goldthread.aliases import AliasTable
from goldthread.answerer import ask
from goldthread.audit import AuditLog
from goldthread.budget import BudgetExceeded, BudgetGuard
from goldthread.config import Pack, pack_version
from goldthread.models.base import Connector, Prompt
from goldthread.search import search
from goldthread.store import Store
from goldthread.verifier import verify_quote

SUCCESS_THRESHOLDS = {"retrieval_hit_rate": 0.80, "not_found_accuracy": 1.0, "verified_quote_integrity": 1.0}
JUDGE_SYSTEM = ("Grade whether the answer covers the expected key point. "
                "Reply with verdict yes, partial or no and a one-sentence reason.")
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["yes", "partial", "no"]}, "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


@dataclass
class CaseResult:
    id: str
    status: str
    answer_kind: str
    retrieval_hit: bool | None
    expected_cited: bool | None
    not_found_ok: bool
    quotes_total: int
    quotes_verified: int
    judge: str
    integrity_failures: int = 0


@dataclass
class EvalReport:
    run_id: str
    pack_version: str
    models: dict[str, str]
    results: list[CaseResult] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    stopped: str | None = None
    remaining: list[str] = field(default_factory=list)


def _report_paths(pack: Pack, run_id: str) -> tuple[Path, Path]:
    folder = pack.data_dir / "reports"
    return folder / f"eval-{run_id}.md", folder / f"eval-{run_id}.json"


def _save_json(pack: Pack, report: EvalReport) -> Path:
    path = _report_paths(pack, report.run_id)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return path


def _load_results(pack: Pack, run_id: str) -> list[CaseResult]:
    path = _report_paths(pack, run_id)[1]
    if not path.is_file():
        return []
    return [CaseResult(**r) for r in json.loads(path.read_text(encoding="utf-8"))["results"]]


def _judge(pack: Pack, connector: Connector, guard: BudgetGuard, question: str, expected: str, answer: str) -> str:
    spec = pack.models["judge"]
    prompt = Prompt(JUDGE_SYSTEM, f"QUESTION: {question}\nEXPECTED: {expected}\nANSWER: {answer}", schema=JUDGE_SCHEMA)
    guard.check("judge", spec.model, connector.hosted, connector.estimate_input_tokens(spec, prompt), spec.max_tokens)
    started = time.monotonic()
    raw = connector.structured(spec, prompt)
    guard.record("judge", spec.model, raw.served_by, connector.hosted, raw.usage, raw.fallback,
                 time.monotonic() - started)
    return str(raw.data.get("verdict", "")) if raw.data else raw.stop_reason


def _metrics(results: list[CaseResult]) -> dict[str, float]:
    approved = [r for r in results if r.status == "approved"]
    if not approved:
        return {}
    retrieval = [r.retrieval_hit for r in approved if r.retrieval_hit is not None]
    cited = [r.expected_cited for r in approved if r.expected_cited is not None]
    ok_quotes = sum(r.quotes_verified for r in approved)
    judged = [r.judge for r in approved if r.judge]
    return {
        "retrieval_hit_rate": sum(retrieval) / len(retrieval) if retrieval else 1.0,
        "not_found_accuracy": sum(r.not_found_ok for r in approved) / len(approved),
        "verified_quote_integrity": ((ok_quotes - sum(r.integrity_failures for r in approved)) / ok_quotes
                                     if ok_quotes else 1.0),
        "expected_source_cited_rate": sum(cited) / len(cited) if cited else 1.0,
        "judge_yes_rate": judged.count("yes") / len(judged) if judged else 1.0,
    }


def run_eval(pack: Pack, store: Store, aliases: AliasTable, connectors: Mapping[str, Connector], guard: BudgetGuard,
             audit: AuditLog, run_id: str, resume: bool = False) -> EvalReport:
    report = EvalReport(run_id, pack_version(pack), {job: pack.models[job].model for job in ("answer", "judge")})
    if resume:
        report.results = _load_results(pack, run_id)
    done = {r.id for r in report.results}
    order = {case.id: i for i, case in enumerate(pack.tests)}

    for i, case in enumerate(pack.tests):
        if case.id in done:
            continue
        hits = [h.passage.address for h in search(store, aliases, case.question, k=10)]
        try:
            answer = ask(pack, store, aliases, connectors["answer"], pack.models["answer"], guard, audit,
                         case.question, run_id)
            citations = [c for s in answer.statements for c in s.citations]
            judge = ""
            if case.status == "approved" and case.expected_point and answer.kind == "answer":
                judge = _judge(pack, connectors["judge"], guard, case.question, case.expected_point,
                               " ".join(s.text for s in answer.statements))
        except BudgetExceeded as exc:
            report.stopped = f"budget: {exc.limit} limit"
            report.remaining = [c.id for c in pack.tests[i:] if c.id not in done]
            break
        sources = case.expected_sources
        report.results.append(CaseResult(
            id=case.id, status=case.status, answer_kind=answer.kind,
            retrieval_hit=any(a.startswith(s) for s in sources for a in hits) if sources else None,
            expected_cited=any(c.address.startswith(s) for s in sources for c in citations) if sources else None,
            not_found_ok=case.expect_not_found == (answer.kind == "not_found"),
            quotes_total=len(citations), quotes_verified=sum(c.ok for c in citations), judge=judge,
            integrity_failures=sum(1 for c in citations if c.ok and not verify_quote(store, c.address, c.quote).ok),
        ))
        report.results.sort(key=lambda r: order.get(r.id, len(order)))
        _save_json(pack, report)

    report.metrics = _metrics(report.results)
    report.passed = (report.stopped is None and bool(report.metrics)
                     and all(report.metrics[k] >= v for k, v in SUCCESS_THRESHOLDS.items()))
    _save_json(pack, report)
    return report


def render_eval_report_md(report: EvalReport) -> str:
    models = ", ".join(f"{job}={model}" for job, model in report.models.items())
    lines = [f"# Evaluation report — run {report.run_id}", "",
             f"Pack version: {report.pack_version} · Models: {models}", "",
             f"Result: **{'PASSED' if report.passed else 'FAILED'}**"
             + (f" (stopped: {report.stopped})" if report.stopped else ""), "",
             "## Metrics (approved questions only)", "", "| metric | value | threshold |", "|---|---|---|"]
    for name, value in report.metrics.items():
        threshold = SUCCESS_THRESHOLDS.get(name)
        lines.append(f"| {name} | {value:.2f} | {'≥ %.2f' % threshold if threshold is not None else '—'} |")
    if not report.metrics:
        lines.append("| no approved questions | — | — |")
    lines += ["", "## Questions", "",
              "| id | status | answer | right source found | expected source cited | not-found correct | "
              "quotes verified | judge |", "|---|---|---|---|---|---|---|---|"]
    show = {True: "yes", False: "no", None: "—"}
    for r in report.results:
        lines.append(f"| {r.id} | {r.status} | {r.answer_kind} | {show[r.retrieval_hit]} | {show[r.expected_cited]} | "
                     f"{show[r.not_found_ok]} | {r.quotes_verified}/{r.quotes_total} | {r.judge or '—'} |")
    if report.remaining:
        lines += ["", f"Not run (resume with --resume {report.run_id}): {', '.join(report.remaining)}"]
    lines += ["", "Draft questions are run and listed but not counted in the metrics."]
    return "\n".join(lines) + "\n"


def write_eval_report(pack: Pack, report: EvalReport) -> tuple[Path, Path]:
    md_path, _ = _report_paths(pack, report.run_id)
    json_path = _save_json(pack, report)
    md_path.write_text(render_eval_report_md(report), encoding="utf-8")
    return md_path, json_path
