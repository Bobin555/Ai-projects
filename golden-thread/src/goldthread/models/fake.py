"""Deterministic connector for tests: no network, no randomness."""
from __future__ import annotations

import re
from typing import Mapping

from goldthread.core import ModelSpec, Usage
from goldthread.models.base import NOT_FOUND, Prompt, RawAnswer, RawBlock, RawCitation, RawStructured

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
_WORD = re.compile(r"\w+")


def _first_sentence(text: str) -> str:
    return _SENTENCE_END.split(" ".join(text.split()), maxsplit=1)[0]


def _line_after(label: str, text: str) -> str:
    for line in text.splitlines():
        if line.startswith(label):
            return line[len(label):].strip()
    return ""


class FakeConnector:
    def __init__(self, script: Mapping[str, object] | None = None,
                 extractions: Mapping[str, list[dict]] | None = None,
                 hosted: bool = False, provider: str = "fake"):
        self.script = dict(script or {})
        self.extractions = dict(extractions or {})
        self.hosted = hosted
        self.provider = provider

    def estimate_input_tokens(self, spec: ModelSpec, prompt: Prompt) -> int:
        return (len(prompt.system) + len(prompt.user_text) + sum(len(p.text) for p in prompt.passages)) // 4

    def _usage(self, spec: ModelSpec, prompt: Prompt, output: str) -> Usage:
        return Usage(self.estimate_input_tokens(spec, prompt), len(output) // 4)

    def answer(self, spec: ModelSpec, prompt: Prompt) -> RawAnswer:
        scripted = self.script.get(prompt.user_text)
        stop_reason = "end_turn"
        if scripted == "REFUSE":
            blocks: tuple[RawBlock, ...] = ()
            stop_reason = "refusal"
        elif scripted == NOT_FOUND:
            blocks = (RawBlock(NOT_FOUND, ()),)
        elif scripted is not None:
            blocks = tuple(scripted)  # a list of RawBlock
        else:
            texts = [p for p in prompt.passages if p.kind == "text" and p.text.strip()][:2]
            blocks = tuple(RawBlock(s, (RawCitation(p.address, s),)) for p in texts for s in [_first_sentence(p.text)])
        output = " ".join(b.text for b in blocks)
        return RawAnswer(blocks, stop_reason, spec.model, False, self._usage(spec, prompt, output))

    def structured(self, spec: ModelSpec, prompt: Prompt) -> RawStructured:
        properties = (prompt.schema or {}).get("properties") or {}
        if "verdict" in properties:
            expected = {w.lower() for w in _WORD.findall(_line_after("EXPECTED:", prompt.user_text))}
            answer = prompt.user_text.split("ANSWER:", 1)[1] if "ANSWER:" in prompt.user_text else ""
            words = {w.lower() for w in _WORD.findall(answer)}
            verdict = "yes" if expected and expected <= words else "no"
            data: Mapping = {"verdict": verdict, "reason": "fake judge: word overlap"}
        else:
            first_line = prompt.user_text.splitlines()[0] if prompt.user_text else ""
            chunk_id = first_line[len("CHUNK: "):].strip() if first_line.startswith("CHUNK: ") else ""
            data = {"records": list(self.extractions.get(chunk_id, []))}
        return RawStructured(data, "end_turn", spec.model, False, self._usage(spec, prompt, str(data)))
