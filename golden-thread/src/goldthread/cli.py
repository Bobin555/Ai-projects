"""Command line: goldthread --pack PATH [--data-root PATH] <command>."""
from __future__ import annotations

import argparse
import secrets
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from goldthread.aliases import AliasTable
from goldthread.answerer import ask
from goldthread.audit import AuditLog
from goldthread.budget import BudgetExceeded, BudgetGuard, Ledger, PriceTable, render_cost_summary, summarise, validate_prices
from goldthread.checks import render_checks_md, run_checks
from goldthread.config import Pack, PackError, load_pack
from goldthread.evaluate import render_eval_report_md, run_eval, write_eval_report
from goldthread.extractor import extract_pack, extraction_status
from goldthread.fetch import OfflineError, fetch_pack
from goldthread.ingest import ingest_pack
from goldthread.linker import link_records
from goldthread.models import get_connector
from goldthread.netguard import NetworkBlocked, no_network
from goldthread.render import render_answer_html, render_answer_md
from goldthread.review import export_review, import_review
from goldthread.search import search
from goldthread.store import Store
from goldthread.trace import render_trace_md, trace

EXIT_OK, EXIT_ERROR, EXIT_BUDGET = 0, 1, 3


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goldthread", description="Traceable question-answering over a pack of documents.")
    parser.add_argument("--pack", required=True, help="path to the pack folder")
    parser.add_argument("--data-root", help="where pack data lives (default: $GT_DATA_DIR or ./data)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    sub.add_parser("fetch", help="download registered documents and record their checksums")
    sub.add_parser("ingest", help="read registered documents into the store")
    p = sub.add_parser("search", help="show matching passages (no model call)")
    p.add_argument("question")
    p = sub.add_parser("extract", help="extract records with the model, then link them")
    p.add_argument("--resume", metavar="RUN_ID")
    p.add_argument("--docs", nargs="+", metavar="DOC_ID", default=[])
    p = sub.add_parser("review-export", help="write draft records to a review sheet")
    p.add_argument("--out")
    p = sub.add_parser("review-import", help="apply a reviewed sheet")
    p.add_argument("path")
    p.add_argument("--reviewer", required=True)
    p = sub.add_parser("ask", help="answer a question with verified quotes")
    p.add_argument("question")
    p.add_argument("--html", action="store_true")
    p = sub.add_parser("trace", help="trace a requirement code or record id")
    p.add_argument("code")
    sub.add_parser("check", help="coverage checks and superseded citations")
    p = sub.add_parser("test", help="run the pack's test questions")
    p.add_argument("--resume", metavar="RUN_ID")
    sub.add_parser("spend", help="spend this month and for the last run")
    return parser


class Context:
    def __init__(self, pack: Pack):
        self.pack = pack
        self.store = Store(pack.data_dir / "store.sqlite3")
        self.aliases = AliasTable.from_csv(pack.aliases_path)
        self.ledger = Ledger(pack.data_dir / "ledger.sqlite3")
        self.audit = AuditLog(pack.data_dir / "audit.jsonl")
        self.prices = PriceTable.load()

    def guard(self, run_id: str) -> BudgetGuard:
        validate_prices(self.pack, self.prices)
        return BudgetGuard(self.pack.budget, self.ledger, self.prices, run_id)

    def connector(self, job: str):
        return get_connector(self.pack.models[job].provider, pack=self.pack)

    def cost(self, run_id: str) -> None:
        print(render_cost_summary(summarise(self.ledger, self.pack.budget, run_id)), file=sys.stderr)


def _budget_stop(ctx: Context, command: str, stopped: str, run_id: str, remaining: Sequence[str]) -> int:
    print(f"Stopped: {stopped}. Not processed: {', '.join(remaining)}", file=sys.stderr)
    print(f"Raise the limit in pack.yaml, then resume with: goldthread --pack {ctx.pack.root} {command} "
          f"--resume {run_id}", file=sys.stderr)
    return EXIT_BUDGET


def cmd_fetch(ctx: Context, args) -> int:
    report = fetch_pack(ctx.pack)
    for label, items in (("downloaded", report.downloaded), ("checksums recorded", report.recorded_checksums),
                         ("already present", report.already_present), ("CHECKSUM MISMATCH (quarantined)", report.mismatched),
                         ("failed", report.failed)):
        print(f"{label}: {len(items)}" + "".join(f"\n  - {i}" for i in items))
    return EXIT_ERROR if report.mismatched or report.failed else EXIT_OK


def cmd_ingest(ctx: Context, args) -> int:
    report = ingest_pack(ctx.pack, ctx.store)
    print(f"documents: {report.documents} · passages: {report.passages}")
    print(f"flagged passages (no text layer or withheld): {len(report.flagged)}"
          + "".join(f"\n  - {a}" for a in report.flagged))
    print(f"skipped: {len(report.skipped)}" + "".join(f"\n  - {s}" for s in report.skipped))
    return EXIT_ERROR if report.skipped else EXIT_OK


def cmd_search(ctx: Context, args) -> int:
    hits = search(ctx.store, ctx.aliases, args.question)
    if not hits:
        print("No matching passages.")
    for h in hits:
        snippet = " ".join(h.passage.text.split())[:160]
        print(f"{h.passage.address}  [{h.passage.kind}]  {h.passage.heading}\n    {snippet}")
    return EXIT_OK


def cmd_extract(ctx: Context, args) -> int:
    run_id = args.resume or new_run_id()
    report = extract_pack(ctx.pack, ctx.store, ctx.connector("extract"), ctx.pack.models["extract"],
                          ctx.guard(run_id), ctx.audit, run_id, resume=bool(args.resume), only_docs=args.docs)
    links = link_records(ctx.store, ctx.pack.schema, ctx.aliases)
    print(f"run {report.run_id}: chunks {report.chunks_done}/{report.chunks_total} · new records {report.records_new} · "
          f"flagged {report.records_flagged} · links created {links.created}, removed {links.removed}")
    for item in report.failed_chunks:
        print(f"  ⚠ chunk failed: {item}")
    if links.unresolved:
        print(f"unresolved links: {len(links.unresolved)}" + "".join(f"\n  - {u}" for u in links.unresolved))
    ctx.cost(report.run_id)
    if report.stopped:
        return _budget_stop(ctx, "extract", report.stopped, report.run_id, report.remaining_chunks)
    return EXIT_OK


def cmd_review_export(ctx: Context, args) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(args.out) if args.out else ctx.pack.data_dir / "review" / f"review-{stamp}.csv"
    n = export_review(ctx.store, path)
    print(f"{n} draft records written to {path}")
    return EXIT_OK


def cmd_review_import(ctx: Context, args) -> int:
    report = import_review(ctx.store, Path(args.path), args.reviewer)
    print(f"applied: {report.applied}")
    for row in report.rejected_rows:
        print(f"  rejected {row}")
    for record_id in report.reverified_failed:
        print(f"  ⚠ {record_id}: quote does not match the source; left as draft")
    links = link_records(ctx.store, ctx.pack.schema, ctx.aliases)  # decisions change which links hold
    print(f"links recomputed: {links.created} added, {links.removed} removed")
    return EXIT_ERROR if report.rejected_rows else EXIT_OK


def cmd_ask(ctx: Context, args) -> int:
    run_id = new_run_id()
    try:
        answer = ask(ctx.pack, ctx.store, ctx.aliases, ctx.connector("answer"), ctx.pack.models["answer"],
                     ctx.guard(run_id), ctx.audit, args.question, run_id)
    except BudgetExceeded as exc:
        print(f"Stopped: {exc}. No model call was made.", file=sys.stderr)
        print("Raise the limit in pack.yaml, or wait for next month's budget, then ask again.", file=sys.stderr)
        return EXIT_BUDGET
    render = render_answer_html if args.html else render_answer_md
    print(render(answer, ctx.pack.outside))
    ctx.cost(run_id)
    return EXIT_ERROR if answer.kind in ("refused", "incomplete") else EXIT_OK


def cmd_trace(ctx: Context, args) -> int:
    titles = {d.key: d.title for d in ctx.store.documents()}
    searched, not_extracted = [], []
    for key, (done, total) in extraction_status(ctx.pack, ctx.store).items():
        label = f"{key} — {titles.get(key, '')}"
        if key not in titles:
            not_extracted.append(f"{label} (not ingested)")
        elif total == 0:
            not_extracted.append(f"{label} (no extractable text)")
        elif done == total:
            searched.append(label)
        else:
            not_extracted.append(label + (f" (partly extracted: {done}/{total} chunks)" if done else ""))
    print(render_trace_md(trace(ctx.store, ctx.aliases, args.code), searched, not_extracted))
    return EXIT_OK


def cmd_check(ctx: Context, args) -> int:
    print(render_checks_md(run_checks(ctx.store, ctx.pack.schema)))
    return EXIT_OK


def cmd_test(ctx: Context, args) -> int:
    run_id = args.resume or new_run_id()
    connectors = {"answer": ctx.connector("answer"), "judge": ctx.connector("judge")}
    report = run_eval(ctx.pack, ctx.store, ctx.aliases, connectors, ctx.guard(run_id), ctx.audit, run_id,
                      resume=bool(args.resume))
    md_path, json_path = write_eval_report(ctx.pack, report)
    print(render_eval_report_md(report))
    print(f"Report written to {md_path} and {json_path}")
    ctx.cost(report.run_id)
    if report.stopped:
        return _budget_stop(ctx, "test", report.stopped, report.run_id, report.remaining)
    return EXIT_OK if report.passed else EXIT_ERROR


def cmd_spend(ctx: Context, args) -> int:
    last = ctx.ledger.last_run_id()
    if last is None:
        print("No spend recorded yet.")
        return EXIT_OK
    print(render_cost_summary(summarise(ctx.ledger, ctx.pack.budget, last)))
    return EXIT_OK


COMMANDS = {"fetch": cmd_fetch, "ingest": cmd_ingest, "search": cmd_search, "extract": cmd_extract,
            "review-export": cmd_review_export, "review-import": cmd_review_import, "ask": cmd_ask,
            "trace": cmd_trace, "check": cmd_check, "test": cmd_test, "spend": cmd_spend}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        pack = load_pack(Path(args.pack), Path(args.data_root) if args.data_root else None)
        if args.command == "fetch" and pack.offline:
            raise OfflineError("offline pack: fetch is disabled")
        with no_network() if pack.offline else nullcontext():
            return COMMANDS[args.command](Context(pack), args)
    except (PackError, OfflineError, NetworkBlocked, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
