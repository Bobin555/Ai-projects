"""Connector interface shared by every model provider."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from goldthread.core import ModelSpec, Passage, Usage

NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class Prompt:
    system: str
    user_text: str
    passages: tuple[Passage, ...] = ()
    titles: Mapping[str, str] = field(default_factory=dict)  # address -> source title shown to the model
    schema: Mapping | None = None


@dataclass(frozen=True)
class RawCitation:
    address: str
    quote: str


@dataclass(frozen=True)
class RawBlock:
    text: str
    citations: tuple[RawCitation, ...]


Iterations = tuple[tuple[str, Usage], ...]  # (model, usage) per attempt when the provider falls back


@dataclass(frozen=True)
class RawAnswer:
    blocks: tuple[RawBlock, ...]
    stop_reason: str
    served_by: str
    fallback: bool
    usage: Usage
    iterations: Iterations = ()


@dataclass(frozen=True)
class RawStructured:
    data: Mapping
    stop_reason: str
    served_by: str
    fallback: bool
    usage: Usage
    iterations: Iterations = ()


class Connector(Protocol):
    provider: str
    hosted: bool
    fallback: bool  # the provider may retry on another model, so a call can cost more than one attempt

    def estimate_input_tokens(self, spec: ModelSpec, prompt: Prompt) -> int: ...

    def answer(self, spec: ModelSpec, prompt: Prompt) -> RawAnswer: ...

    def structured(self, spec: ModelSpec, prompt: Prompt) -> RawStructured: ...
