"""Review sheets: export draft records for an engineer, import their decisions."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from goldthread.core import Record, RecordSchema
from goldthread.records import missing_required
from goldthread.store import Store
from goldthread.verifier import verify_quote

REVIEW_COLUMNS = ["id", "type", "status", "address", "quote", "fields_json", "quote_check", "decision",
                  "corrected_fields_json", "corrected_quote", "note"]
DECISIONS = ("verified", "corrected", "rejected")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ImportReport:
    applied: int = 0
    rejected_rows: list[str] = field(default_factory=list)  # "row <n>: <reason>"
    reverified_failed: list[str] = field(default_factory=list)  # record ids
    missing_fields: list[str] = field(default_factory=list)  # record ids left as draft: a required field is empty


def export_review(store: Store, path: Path, statuses: Sequence[str] = ("draft",)) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [r for r in store.records() if r.status in statuses]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for r in records:
            check = verify_quote(store, r.address, r.quote)
            writer.writerow({
                "id": r.id, "type": r.type, "status": r.status, "address": r.address, "quote": r.quote,
                "fields_json": json.dumps(dict(r.fields), ensure_ascii=False),
                "quote_check": "ok" if check.ok else check.reason,
                "decision": "", "corrected_fields_json": "", "corrected_quote": "", "note": "",
            })
    return len(records)


def _read_sheet(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read the whole sheet before anything is applied, so a bad file changes nothing."""
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            return list(reader.fieldnames or []), list(reader)
    except UnicodeDecodeError as exc:
        raise ValueError(f"review sheet {path} is not UTF-8 (bad byte at position {exc.start}); nothing was applied. "
                         'In Excel use "Save As" > "CSV UTF-8", then import again.') from exc


def _parse_fields(cell: str, label: str, rt_fields: Sequence[str]) -> dict[str, str]:
    """A JSON object of field values; raises ValueError with the reason a row is refused."""
    try:
        parsed = json.loads(cell)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    unknown = [str(k) for k in parsed if str(k) not in rt_fields]
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")
    return {str(k): str(v) for k, v in parsed.items()}


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())


def _decide(rec: Record, row: dict[str, str], columns: Sequence[str], decision: str,
            rt_fields: Sequence[str]) -> tuple[dict[str, str], str]:
    """The fields and quote a verified or corrected row asks for; raises ValueError to refuse the row.
    Edits typed straight into the exported quote or fields_json cells count as corrections, never silently dropped."""
    edited_fields = edited_quote = None
    sheet_fields = (row.get("fields_json") or "").strip()
    if "fields_json" in columns and sheet_fields:
        parsed = _parse_fields(sheet_fields, "fields_json", rt_fields)
        if parsed != dict(rec.fields):
            edited_fields = parsed
    sheet_quote = (row.get("quote") or "").strip()
    if "quote" in columns and sheet_quote and not _same_text(sheet_quote, rec.quote):
        edited_quote = sheet_quote
    if decision == "verified":
        if edited_fields is not None or edited_quote is not None:
            raise ValueError("quote or fields_json was edited; use decision 'corrected' to apply edits")
        return dict(rec.fields), rec.quote
    fields = edited_fields if edited_fields is not None else dict(rec.fields)
    quote = edited_quote if edited_quote is not None else rec.quote
    corrected_fields = (row.get("corrected_fields_json") or "").strip()
    if corrected_fields:
        fields.update(_parse_fields(corrected_fields, "corrected_fields_json", rt_fields))
    if (row.get("corrected_quote") or "").strip():
        quote = row["corrected_quote"].strip()
    return fields, quote


def import_review(store: Store, path: Path, reviewer: str, schema: RecordSchema,
                  now: Callable[[], datetime] = utc_now) -> ImportReport:
    report = ImportReport()
    at = now().strftime("%Y-%m-%dT%H:%M:%SZ")
    columns, rows = _read_sheet(path)
    missing = {"id", "decision"} - set(columns)
    if missing:
        raise ValueError(f"review sheet is missing columns: {', '.join(sorted(missing))}")
    for n, row in enumerate(rows, start=2):  # row 1 is the header, as in a spreadsheet
        decision = (row.get("decision") or "").strip().lower()
        if not decision:
            continue
        record_id = (row.get("id") or "").strip()
        rec = store.record(record_id)
        if rec is None:
            report.rejected_rows.append(f"row {n}: unknown id {record_id}")
            continue
        if decision not in DECISIONS:
            report.rejected_rows.append(f"row {n}: unknown decision '{decision}'")
            continue
        if decision == "rejected":
            store.set_review(rec.id, "rejected", reviewer, at, None, None, rec.flags)
            report.applied += 1
            continue
        rt = schema.record_types.get(rec.type)
        try:
            fields, quote = _decide(rec, row, columns, decision, rt.fields if rt else tuple(rec.fields))
        except ValueError as exc:
            report.rejected_rows.append(f"row {n}: {exc}")
            continue
        check = verify_quote(store, rec.address, quote)
        if not check.ok:
            store.set_review(rec.id, "draft", reviewer, at, fields, quote, (f"quote_failed: {check.reason}",))
            report.reverified_failed.append(rec.id)
            continue
        empty = missing_required(rt, fields) if rt else []
        if empty:
            store.set_review(rec.id, "draft", reviewer, at, fields, quote, tuple(f"missing_field: {f}" for f in empty))
            report.missing_fields.append(rec.id)
            continue
        store.set_review(rec.id, decision, reviewer, at, fields, quote, ())
        report.applied += 1
    return report
