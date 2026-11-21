"""Keyword search with aliases and exact identifiers."""
from __future__ import annotations

import re
from dataclasses import dataclass

from goldthread.aliases import AliasTable, normalise_term
from goldthread.core import Passage
from goldthread.store import Store

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having
he her here hers him his how i if in into is it its itself just me more most my no nor not now of off on
once only or other our ours out over own same she should so some such than that the their them then there
these they this those through to too under until up very was we were what when where which while who whom
why will with would you your yours shall must may might said say says tell show give list find
""".split())

_IDENTIFIER_RES = (re.compile(r"\d+(?:\.\d+)+(?:\([a-z0-9]+\))*"), re.compile(r"\bML\d{5}[A-Z]\d{3}\b"))
_TOKEN = re.compile(r"[A-Za-z0-9]+")
_WORD = re.compile(r"[A-Za-z]{3,}")


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float


def find_identifiers(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for pattern in _IDENTIFIER_RES:
        found.extend((m.start(), m.group(0)) for m in pattern.finditer(text))
    return [s for _, s in sorted(found)]


def _phrase(text: str) -> str:
    return '"' + " ".join(t.lower() for t in _TOKEN.findall(text)) + '"'


def _bounded(term: str) -> re.Pattern[str]:
    """The normalised term as a whole token run: "pdc 1" does not match inside "pdc 10", nor "se" inside "release"."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalise_term(term)) + r"(?![a-z0-9])")


def _filters(question: str, aliases: AliasTable) -> list[str]:
    """Terms a passage must contain: exact identifiers, and numbered alias groups (PDC 10, RG 1.232). Acronym groups
    such as SE or PDC widen the keyword search but never filter, or "PDC 16" would pass for a "PDC 10" question."""
    terms = find_identifiers(question)
    for canon in aliases.find(question):
        variants = aliases.variants(canon)
        if any(ch.isdigit() for v in variants for ch in v):
            terms.extend(variants)
    return terms


def build_match_expr(question: str, aliases: AliasTable) -> str:
    terms: list[str] = [_phrase(i) for i in find_identifiers(question)]
    strip = list(find_identifiers(question))
    for canon in aliases.find(question):
        for variant in aliases.variants(canon):
            terms.append(_phrase(variant))
            strip.append(variant)
    remaining = normalise_term(question)
    for term in sorted(strip, key=len, reverse=True):  # longest first: "mhtgr dc criterion 10" before "criterion 10"
        remaining = _bounded(term).sub(" ", remaining)
    terms.extend(f'"{w}"' for w in _WORD.findall(remaining) if w not in STOPWORDS)
    terms = [t for t in dict.fromkeys(terms) if t != '""']
    return " OR ".join(terms)


def _contains(haystack: str, needle: str) -> bool:
    return _bounded(needle).search(normalise_term(haystack)) is not None


def search(store: Store, aliases: AliasTable, question: str, k: int = 10,
           include_superseded: bool = False) -> list[Hit]:
    expr = build_match_expr(question, aliases)
    if not expr:
        return []
    filters = _filters(question, aliases)
    hits: list[Hit] = []
    for passage, score in store.fts_search(expr, include_superseded, k * 5):
        if passage.kind in ("no_text", "heading"):
            continue
        if filters and not any(_contains(passage.heading + "\n" + passage.text, f) for f in filters):
            continue
        hits.append(Hit(passage, score))
        if len(hits) == k:
            break
    return hits
