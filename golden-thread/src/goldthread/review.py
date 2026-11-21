"""Review sheets: export draft records for an engineer, import their decisions."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

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


def import_review(store: Store, path: Path, reviewer: str, now: Callable[[], datetime] = utc_now) -> ImportReport:
    report = ImportReport()
    at = now().strftime("%Y-%m-%dT%H:%M:%SZ")
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"id", "decision"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"review sheet is missing columns: {', '.join(sorted(missing))}")
        for n, row in enumerate(reader, start=2):  # row 1 is the header, as in a spreadsheet
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

            fields, quote = dict(rec.fields), rec.quote
            if decision == "corrected":
                raw_fields = (row.get("corrected_fields_json") or "").strip()
                if raw_fields:
                    try:
                        parsed = json.loads(raw_fields)
                    except json.JSONDecodeError:
                        report.rejected_rows.append(f"row {n}: invalid corrected_fields_json")
                        continue
                    if not isinstance(parsed, dict):
                        report.rejected_rows.append(f"row {n}: corrected_fields_json must be a JSON object")
                        continue
                    fields.update({str(k): str(v) for k, v in parsed.items()})
                if (row.get("corrected_quote") or "").strip():
                    quote = row["corrected_quote"].strip()

            check = verify_quote(store, rec.address, quote)
            if not check.ok:
                store.set_review(rec.id, "draft", reviewer, at, fields, quote, (f"quote_failed: {check.reason}",))
                report.reverified_failed.append(rec.id)
                continue
            store.set_review(rec.id, decision, reviewer, at, fields, quote, ())
            report.applied += 1
    return report
