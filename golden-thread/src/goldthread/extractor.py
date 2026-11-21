"""Extract records from documents, section by section, with budget stops and resume."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from goldthread.audit import AuditLog
from goldthread.budget import BudgetExceeded, BudgetGuard
from goldthread.config import Pack
from goldthread.core import LayoutRecipe, ModelSpec, Passage, Record
from goldthread.models.base import Connector, Prompt
from goldthread.records import extraction_schema, missing_required, record_id
from goldthread.store import Store
from goldthread.verifier import verify_quote

EXTRACT_SYSTEM = """You extract structured records from one section of a controlled document.
Rules:
- Extract only the record types listed below.
- Each record's quote must be copied verbatim from the passage named in its address. Do not paraphrase, and do not join text from different passages.
- Give each record a key (k1, k2, ...) unique within this section, and use those keys for cross-references between records in this section.
- Leave a field empty rather than guess.
- Never infer text that is marked as withheld or redacted.
- If the section has nothing to extract, return an empty list of records."""


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    revision: str
    heading: str
    passages: tuple[Passage, ...]


@dataclass
class ExtractReport:
    run_id: str
    chunks_total: int = 0
    chunks_done: int = 0
    records_new: int = 0
    records_flagged: int = 0
    stopped: str | None = None
    remaining_chunks: list[str] = field(default_factory=list)
    failed_chunks: list[str] = field(default_factory=list)  # "<chunk id>: <stop reason>"


def _top_heading(p: Passage) -> str:
    return p.heading.split(" > ")[0] if p.heading else ""


def make_chunks(passages: Sequence[Passage], max_chars: int = 12000) -> list[Chunk]:
    chunks: list[Chunk] = []
    counters: dict[str, int] = {}
    current: list[Passage] = []

    def flush() -> None:
        if current:
            first = current[0]
            doc_key = f"{first.doc_id}@{first.revision}"
            index = counters.get(doc_key, 0)
            counters[doc_key] = index + 1
            chunks.append(Chunk(f"{doc_key}#{index}", first.doc_id, first.revision, _top_heading(first),
                                tuple(current)))
            current.clear()

    size = 0
    for p in passages:
        if p.kind == "no_text":
            continue
        if current:
            last = current[-1]
            same_group = (p.doc_id, p.revision, _top_heading(p)) == (last.doc_id, last.revision, _top_heading(last))
            if not same_group or size + len(p.text) > max_chars:
                flush()
                size = 0
        current.append(p)
        size += len(p.text)
    flush()
    return chunks


def extract_system(recipe: LayoutRecipe) -> str:
    return (f"{EXTRACT_SYSTEM}\n\nRecord types: {', '.join(recipe.looks_for)}\n\n"
            f"Layout instructions:\n{recipe.instructions}\n\nExample:\n{recipe.example}")


def chunk_user_text(chunk: Chunk, title: str) -> str:
    head = f"CHUNK: {chunk.id}\nDOCUMENT: {title} ({chunk.doc_id}@{chunk.revision})\nSECTION: {chunk.heading}\n\n"
    return head + "".join(f"[{p.address}]" + (f" ({p.heading})" if p.heading else "") + f"\n{p.text}\n\n"
                          for p in chunk.passages)


def _to_record(pack: Pack, store: Store, chunk: Chunk, item: Mapping, served_by: str, run_id: str) -> Record | None:
    rt = pack.schema.record_types.get(str(item.get("type", "")))
    if rt is None:
        return None
    fields = {str(f.get("name", "")): str(f.get("value", "")) for f in item.get("fields") or [] if f.get("name")}
    if "key" in rt.fields and item.get("key") and not fields.get("key"):
        fields["key"] = str(item["key"])
    address, quote = str(item.get("address", "")), str(item.get("quote", ""))
    flags = []
    check = verify_quote(store, address, quote)
    if not check.ok:
        flags.append(f"quote_failed: {check.reason}")
    flags += [f"missing_field: {name}" for name in missing_required(rt, fields)]
    return Record(record_id(rt, address, quote, fields), rt.name, fields, address, quote, "draft", tuple(flags),
                  extracted_by=served_by, run_id=run_id, chunk_id=chunk.id)


def extraction_status(pack: Pack, store: Store) -> dict[str, tuple[int, int]]:
    """Document key -> (chunks extracted in any run, chunks in the document), for issued documents with a layout."""
    done = store.chunks_done_any_run()
    status: dict[str, tuple[int, int]] = {}
    for entry in pack.register:
        if entry.status != "issued" or entry.layout not in pack.layouts:
            continue
        ids = [c.id for c in make_chunks(store.passages_of(entry.doc_id, entry.revision))]
        status[entry.key] = (sum(i in done for i in ids), len(ids))
    return status


def extract_pack(pack: Pack, store: Store, connector: Connector, spec: ModelSpec, guard: BudgetGuard,
                 audit: AuditLog, run_id: str, resume: bool = False, only_docs: Sequence[str] = ()) -> ExtractReport:
    wanted = set(only_docs)
    work: list[tuple[Chunk, LayoutRecipe, str]] = []
    for entry in pack.register:
        if entry.status != "issued" or entry.layout not in pack.layouts:
            continue
        if wanted and entry.doc_id not in wanted and entry.key not in wanted:
            continue
        for chunk in make_chunks(store.passages_of(entry.doc_id, entry.revision)):
            work.append((chunk, pack.layouts[entry.layout], entry.title))

    done = store.chunks_done(run_id) if resume else set()
    report = ExtractReport(run_id, chunks_total=len(work))
    for i, (chunk, recipe, title) in enumerate(work):
        if chunk.id in done:
            report.chunks_done += 1
            continue
        schema = extraction_schema(pack.schema, recipe.looks_for, [p.address for p in chunk.passages])
        prompt = Prompt(extract_system(recipe), chunk_user_text(chunk, title), chunk.passages, schema=schema)
        try:
            guard.check("extract", spec.model, connector.hosted, connector.estimate_input_tokens(spec, prompt),
                        spec.max_tokens, fallback=connector.fallback)
        except BudgetExceeded as exc:
            report.stopped = f"budget: {exc.limit} limit"
            report.remaining_chunks = [c.id for c, _, _ in work[i:] if c.id not in done]
            break
        started = time.monotonic()
        raw = connector.structured(spec, prompt)
        cost = guard.record("extract", spec.model, raw.served_by, connector.hosted, raw.usage, raw.fallback,
                            time.monotonic() - started, iterations=raw.iterations).cost_usd
        if raw.stop_reason != "end_turn":
            report.failed_chunks.append(f"{chunk.id}: {raw.stop_reason}")
        stored = flagged = 0
        items = raw.data.get("records", []) if isinstance(raw.data, Mapping) else []
        for item in items:
            rec = _to_record(pack, store, chunk, item, raw.served_by, run_id)
            if rec is None:
                continue
            if store.record(rec.id) is None:
                report.records_new += 1
            store.upsert_record(rec)
            stored += 1
            flagged += bool(rec.flags)
        report.records_flagged += flagged
        store.mark_chunk_done(run_id, chunk.id)
        report.chunks_done += 1
        audit.write("extract_chunk", run_id=run_id, chunk=chunk.id, records=stored, flagged=flagged,
                    stop_reason=raw.stop_reason, served_by=raw.served_by, cost_usd=cost)
    return report
