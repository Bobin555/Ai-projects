"""Claude connector: search-result citations for answers, structured output for extraction."""
from __future__ import annotations

import json

from goldthread.core import ModelSpec, Usage
from goldthread.models.base import Prompt, RawAnswer, RawBlock, RawCitation, RawStructured

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _usage(raw) -> Usage:
    return Usage(getattr(raw, "input_tokens", 0) or 0, getattr(raw, "output_tokens", 0) or 0,
                 getattr(raw, "cache_read_input_tokens", 0) or 0,
                 getattr(raw, "cache_creation_input_tokens", 0) or 0)


class ClaudeConnector:
    provider = "claude"
    hosted = True

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    # --- request pieces -------------------------------------------------------

    @staticmethod
    def _answer_messages(prompt: Prompt) -> list[dict]:
        blocks = [
            {"type": "search_result", "source": p.address, "title": prompt.titles[p.address],
             "content": [{"type": "text", "text": p.text}], "citations": {"enabled": True}}
            for p in prompt.passages if p.text.strip()
        ]
        blocks.append({"type": "text", "text": prompt.user_text})
        return [{"role": "user", "content": blocks}]

    @staticmethod
    def _structured_system(prompt: Prompt) -> list[dict]:
        return [{"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}]

    # --- Connector ------------------------------------------------------------

    def estimate_input_tokens(self, spec: ModelSpec, prompt: Prompt) -> int:
        if prompt.schema is None:
            system, messages = prompt.system, self._answer_messages(prompt)
        else:
            system, messages = self._structured_system(prompt), [{"role": "user", "content": prompt.user_text}]
        tokens = self.client.messages.count_tokens(model=spec.model, system=system, messages=messages).input_tokens
        if prompt.schema is not None:
            tokens += len(json.dumps(prompt.schema)) // 3
        return tokens

    def answer(self, spec: ModelSpec, prompt: Prompt) -> RawAnswer:
        response = self.client.beta.messages.create(
            model=spec.model, max_tokens=spec.max_tokens,
            betas=[FALLBACK_BETA], fallbacks="default",
            output_config={"effort": spec.effort},
            system=prompt.system,
            messages=self._answer_messages(prompt),
        )
        blocks, fallback = [], False
        for block in response.content:
            if block.type == "fallback":
                fallback = True
            elif block.type == "text":
                citations = tuple(RawCitation(c.source, c.cited_text) for c in (block.citations or [])
                                  if getattr(c, "type", "") == "search_result_location")
                blocks.append(RawBlock(block.text, citations))
        if response.stop_reason == "refusal":
            blocks = []
        return RawAnswer(tuple(blocks), response.stop_reason, response.model, fallback, _usage(response.usage))

    def structured(self, spec: ModelSpec, prompt: Prompt) -> RawStructured:
        response = self.client.beta.messages.create(
            model=spec.model, max_tokens=spec.max_tokens,
            betas=[FALLBACK_BETA], fallbacks="default",
            output_config={"effort": spec.effort, "format": {"type": "json_schema", "schema": dict(prompt.schema)}},
            system=self._structured_system(prompt),
            messages=[{"role": "user", "content": prompt.user_text}],
        )
        fallback = any(b.type == "fallback" for b in response.content)
        stop_reason, data = response.stop_reason, {}
        if stop_reason != "refusal":
            text = next((b.text for b in response.content if b.type == "text"), "")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
                if stop_reason == "end_turn":
                    stop_reason = "invalid_json"
        return RawStructured(data, stop_reason, response.model, fallback, _usage(response.usage))
