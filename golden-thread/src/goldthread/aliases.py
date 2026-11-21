"""Alias table: alternative names mapped to a canonical term."""
from __future__ import annotations

import csv
import re
from pathlib import Path

_HYPHENS = re.compile(r"[-‐‑‒–—]")
_SPACES = re.compile(r"\s+")


def normalise_term(text: str) -> str:
    """Lower case, hyphens as spaces, whitespace collapsed."""
    return _SPACES.sub(" ", _HYPHENS.sub(" ", text.lower())).strip()


class AliasTable:
    def __init__(self, groups: dict[str, list[str]]):
        self._groups = {canon: list(dict.fromkeys([canon, *variants])) for canon, variants in groups.items()}
        self._lookup = {normalise_term(v): canon for canon, vs in self._groups.items() for v in vs}
        self._patterns = {
            canon: [re.compile(r"(?<![a-z0-9])" + re.escape(normalise_term(v)) + r"(?![a-z0-9])") for v in vs]
            for canon, vs in self._groups.items()
        }

    @classmethod
    def from_csv(cls, path: Path) -> "AliasTable":
        groups: dict[str, list[str]] = {}
        with Path(path).open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                canon, alias = (row.get("canonical") or "").strip(), (row.get("alias") or "").strip()
                if canon:
                    groups.setdefault(canon, [])
                    if alias:
                        groups[canon].append(alias)
        return cls(groups)

    def find(self, text: str) -> list[str]:
        norm = normalise_term(text)
        return [canon for canon, patterns in self._patterns.items() if any(p.search(norm) for p in patterns)]

    def variants(self, canonical: str) -> list[str]:
        return list(self._groups.get(canonical, []))

    def canonical(self, term: str) -> str | None:
        return self._lookup.get(normalise_term(term))
