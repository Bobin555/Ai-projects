"""Dataclasses shared by every module."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

JOBS = ("extract", "answer", "judge")


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    effort: str = "medium"
    max_tokens: int = 16000


@dataclass(frozen=True)
class Budget:
    per_run_usd: float
    per_month_usd: float


@dataclass(frozen=True)
class DocumentEntry:
    doc_id: str
    title: str
    layout: str
    revision: str
    date: str
    status: str  # "issued" | "superseded"
    supersedes: str  # "doc_id@rev" or ""
    url: str
    sha256: str

    @property
    def key(self) -> str:
        return f"{self.doc_id}@{self.revision}"


@dataclass(frozen=True)
class Passage:
    address: str
    doc_id: str
    revision: str
    page: int
    n: int
    heading: str
    text: str
    kind: str  # "text" | "table" | "withheld" | "no_text"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_sources: tuple[str, ...]
    expected_point: str
    expect_not_found: bool
    status: str  # "draft" | "approved"


@dataclass(frozen=True)
class RecordType:
    name: str
    prefix: str
    fields: tuple[str, ...]
    required: tuple[str, ...]


@dataclass(frozen=True)
class LinkType:
    name: str
    from_type: str
    field: str
    targets: Mapping[str, str]  # record type -> field matched there
    scope: str  # "chunk" | "code"
    reverse: bool  # store the link as target -> source


@dataclass(frozen=True)
class CoverageRule:
    name: str
    type: str
    missing_incoming: str = ""
    has_incoming: str = ""
    has_outgoing: str = ""


@dataclass(frozen=True)
class RecordSchema:
    record_types: Mapping[str, RecordType]
    link_types: Mapping[str, LinkType]
    coverage: tuple[CoverageRule, ...]


@dataclass(frozen=True)
class LayoutRecipe:
    layout: str
    looks_for: tuple[str, ...]
    instructions: str
    example: str


@dataclass(frozen=True)
class Record:
    id: str
    type: str
    fields: Mapping[str, str]
    address: str
    quote: str
    status: str  # "draft" | "verified" | "corrected" | "rejected"
    flags: tuple[str, ...] = ()
    extracted_by: str = ""
    run_id: str = ""
    chunk_id: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""


@dataclass(frozen=True)
class Link:
    src: str
    link_type: str
    dst: str
