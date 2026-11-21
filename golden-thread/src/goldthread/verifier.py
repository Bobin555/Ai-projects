"""Deterministic quote verification: no model involved."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from goldthread.store import Store

_CHARS = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
})
_LINE_HYPHEN = re.compile(r"-[ \t]*\n[ \t]*")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Verification:
    ok: bool
    reason: str = ""


def normalise(text: str, join_hyphenation: bool) -> str:
    out = unicodedata.normalize("NFKC", text).translate(_CHARS)
    if join_hyphenation:
        out = _LINE_HYPHEN.sub("", out)
    return _SPACES.sub(" ", out).strip()


def verify_quote(store: Store, address: str, quote: str) -> Verification:
    needle = normalise(quote, False)
    if not needle:
        return Verification(False, "empty quote")
    passage = store.passage(address)
    document = store.document(passage.doc_id, passage.revision) if passage else None
    if passage is None or document is None:
        return Verification(False, "unknown address")
    if document.status != "issued":
        return Verification(False, "cited revision is superseded")
    if needle in normalise(passage.text, False) or needle in normalise(passage.text, True):
        return Verification(True)
    return Verification(False, "quote not found in passage")
