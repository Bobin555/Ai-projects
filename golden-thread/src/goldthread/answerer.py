"""Answer a question from the store: search, ask the model, verify every quote."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from goldthread.aliases import AliasTable
from goldthread.audit import AuditLog
from goldthread.budget import BudgetGuard
from goldthread.config import Pack, pack_version
from goldthread.core import ModelSpec, Passage
from goldthread.models.base import Connector, Prompt, RawBlock
from goldthread.search import search
from goldthread.store import Store
from goldthread.verifier import verify_quote

UNSOURCED_MIN_CHARS = 25
COMPLETE_STOPS = frozenset({"end_turn", "stop_sequence"})  # any other stop (max_tokens, ...) means cut short
_NOT_FOUND_REPLY = re.compile(r"\W*not[_ ]found\W*", re.IGNORECASE)  # NOT_FOUND, "Not found.", **NOT_FOUND**
_DIGIT = re.compile(r"\d")

ANSWER_SYSTEM = """You answer questions about controlled documents, using only the search results provided.
Rules:
- Answer only from the provided search results. Do not use outside knowledge.
- Every sentence that states a fact must be supported by citations to the search results.
- If the search results do not answer the question, reply with exactly NOT_FOUND and nothing else.
- Never guess text that is marked as withheld or redacted; say that it is withheld.
- When you report a finding, always state any conditions or limitations attached to it."""


@dataclass(frozen=True)
class CheckedCitation:
    address: str
    quote: str
    ok: bool
    reason: str


@dataclass(frozen=True)
class Statement:
    text: str
    citations: tuple[CheckedCitation, ...]
    status: str  # verified | flagged | unsourced | connective


@dataclass(frozen=True)
class Answer:
    question: str
    kind: str  # answer | not_found | refused | incomplete (the model stopped early or returned nothing)
    statements: tuple[Statement, ...]
    searched: tuple[str, ...]
    hits: tuple[str, ...]
    model: str
    served_by: str
    run_id: str
    cost_usd: float
    stop_reason: str = ""


def answer_system(pack: Pack) -> str:
    return f"{ANSWER_SYSTEM}\n\nPack rules:\n{pack.rules}\n\nAnswer format:\n{pack.answer_format}"


def _title(store: Store, passage: Passage) -> str:
    document = store.document(passage.doc_id, passage.revision)
    title = document.title if document else passage.doc_id
    return f"{title} — {passage.heading}" if passage.heading else title


def _statement(store: Store, block: RawBlock) -> Statement:
    if block.citations:
        checked = []
        for c in block.citations:
            v = verify_quote(store, c.address, c.quote)
            checked.append(CheckedCitation(c.address, c.quote, v.ok, v.reason))
        status = "verified" if all(c.ok for c in checked) else "flagged"
        return Statement(block.text, tuple(checked), status)
    return Statement(block.text, (), "connective" if _is_connective(block.text) else "unsourced")


def _is_connective(text: str) -> bool:
    """Short linking text ("Based on the results:") needs no source; a short sentence or a number does."""
    t = text.strip()
    return len(t) < UNSOURCED_MIN_CHARS and not _DIGIT.search(t) and not t.endswith((".", "!", "?"))


def ask(pack: Pack, store: Store, aliases: AliasTable, connector: Connector, spec: ModelSpec,
        guard: BudgetGuard, audit: AuditLog, question: str, run_id: str, k: int = 10,
        version: str | None = None) -> Answer:
    searched = tuple(f"{d.key} — {d.title}" for d in store.documents(status="issued"))
    hits = search(store, aliases, question, k=k)
    hit_addresses = tuple(h.passage.address for h in hits)
    served_by, cost, statements, stop_reason = "", 0.0, (), ""
    if not hits:
        kind = "not_found"
    else:
        prompt = Prompt(answer_system(pack), question, tuple(h.passage for h in hits),
                        {h.passage.address: _title(store, h.passage) for h in hits})
        guard.check("answer", spec.model, connector.hosted, connector.estimate_input_tokens(spec, prompt),
                    spec.max_tokens, fallback=connector.fallback)
        started = time.monotonic()
        raw = connector.answer(spec, prompt)
        entry = guard.record("answer", spec.model, raw.served_by, connector.hosted, raw.usage, raw.fallback,
                             time.monotonic() - started, iterations=raw.iterations)
        served_by, cost, stop_reason = raw.served_by, entry.cost_usd, raw.stop_reason
        text = "".join(b.text for b in raw.blocks).strip()
        complete = raw.stop_reason in COMPLETE_STOPS
        if raw.stop_reason == "refusal":
            kind = "refused"
        elif not text:
            kind = "incomplete"  # nothing came back: never reported as "not found"
        elif complete and _NOT_FOUND_REPLY.fullmatch(text):
            kind = "not_found"
        else:
            kind = "answer" if complete else "incomplete"
            statements = tuple(_statement(store, b) for b in raw.blocks if b.text.strip())
    answer = Answer(question, kind, statements, searched, hit_addresses, spec.model, served_by, run_id, cost,
                    stop_reason)
    audit.write("ask", run_id=run_id, pack_version=version or pack_version(pack), question=question,
                hits=list(hit_addresses), kind=kind, stop_reason=stop_reason, provider=connector.provider,
                model=spec.model, served_by=served_by, cost_usd=cost,
                statements=[{"text": s.text, "status": s.status,
                             "citations": [{"address": c.address, "quote": c.quote, "ok": c.ok, "reason": c.reason}
                                           for c in s.citations]} for s in statements])
    return answer
