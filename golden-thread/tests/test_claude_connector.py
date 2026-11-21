import json
from types import SimpleNamespace as NS

import pytest

from goldthread.core import ModelSpec, Passage, Usage
from goldthread.models.base import Prompt, RawCitation
from goldthread.models.claude import FALLBACK_BETA, ClaudeConnector

ADDR = "SYN-SAR@r2#p1.1"
P = Passage(ADDR, "SYN-SAR", "r2", 1, 1, "3.2 Fuel", "The fuel temperature limit is 1650 C.", "text")
EMPTY = Passage("SYN-SAR@r2#p1.9", "SYN-SAR", "r2", 1, 9, "", "", "no_text")
ANSWER_SPEC = ModelSpec("claude", "claude-opus-5-5", "high", 16000)
EXTRACT_SPEC = ModelSpec("claude", "claude-opus-5-5", "low", 16000)
SCHEMA = {"type": "object", "properties": {"records": {"type": "array"}}, "required": ["records"],
          "additionalProperties": False}


def usage(cache=None):
    return NS(input_tokens=100, output_tokens=50, cache_read_input_tokens=cache, cache_creation_input_tokens=None)


def response(content, model="claude-opus-5-5", stop="end_turn"):
    return NS(content=content, model=model, stop_reason=stop, usage=usage())


class StubClient:
    def __init__(self, resp):
        self.resp, self.calls, self.count_calls = resp, [], []
        self.beta = NS(messages=NS(create=self._create))
        self.messages = NS(count_tokens=self._count)

    def _create(self, **kw):
        self.calls.append(kw)
        return self.resp

    def _count(self, **kw):
        self.count_calls.append(kw)
        return NS(input_tokens=1234)


def text_block(text, citations=None):
    return NS(type="text", text=text, citations=citations)


def cite(source, cited):
    return NS(type="search_result_location", source=source, cited_text=cited, title="t",
              search_result_index=0, start_block_index=0, end_block_index=1)


ANSWER_PROMPT = Prompt("SYSTEM", "What is the limit?", (P, EMPTY), {ADDR: "Synthetic SAR — 3.2 Fuel"})


def test_answer_request_shape():
    client = StubClient(response([text_block("ok")]))
    ClaudeConnector(client).answer(ANSWER_SPEC, ANSWER_PROMPT)
    kw = client.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["max_tokens"] == 16000
    assert kw["betas"] == [FALLBACK_BETA] == ["server-side-fallback-2026-07-01"]
    assert kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "high"} and "format" not in kw["output_config"]
    assert kw["system"] == "SYSTEM"
    assert not {"temperature", "top_p", "top_k"} & set(kw)
    content = kw["messages"][0]["content"]
    assert kw["messages"][0]["role"] == "user" and len(content) == 2  # the empty passage is skipped
    assert content[0] == {"type": "search_result", "source": ADDR, "title": "Synthetic SAR — 3.2 Fuel",
                          "content": [{"type": "text", "text": P.text}], "citations": {"enabled": True}}
    assert content[-1] == {"type": "text", "text": "What is the limit?"}


def test_answer_parses_citations():
    client = StubClient(response([NS(type="thinking", thinking=""),
                                  text_block("The limit is 1650 C.", [cite(ADDR, P.text)]),
                                  text_block(" That is all.", None)]))
    raw = ClaudeConnector(client).answer(ANSWER_SPEC, ANSWER_PROMPT)
    assert [b.text for b in raw.blocks] == ["The limit is 1650 C.", " That is all."]
    assert raw.blocks[0].citations == (RawCitation(ADDR, P.text),) and raw.blocks[1].citations == ()
    assert raw.usage == Usage(100, 50, 0, 0) and raw.stop_reason == "end_turn" and raw.fallback is False


def test_fallback_block_sets_served_by_and_flag():  # Review Focus 5
    client = StubClient(response([NS(type="fallback"), text_block("ok")], model="claude-opus-4-8"))
    raw = ClaudeConnector(client).answer(ANSWER_SPEC, ANSWER_PROMPT)
    assert raw.fallback is True and raw.served_by == "claude-opus-4-8"


def test_refusal_passthrough():
    client = StubClient(response([], stop="refusal"))
    conn = ClaudeConnector(client)
    raw = conn.answer(ANSWER_SPEC, ANSWER_PROMPT)
    assert raw.stop_reason == "refusal" and raw.blocks == ()
    assert conn.structured(EXTRACT_SPEC, Prompt("S", "U", schema=SCHEMA)).data == {}


def test_structured_request_shape():
    client = StubClient(response([text_block('{"records": []}')]))
    ClaudeConnector(client).structured(EXTRACT_SPEC, Prompt("S", "CHUNK: X@r1#0", schema=SCHEMA))
    kw = client.calls[0]
    assert kw["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert kw["system"] == [{"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}]
    assert kw["messages"] == [{"role": "user", "content": "CHUNK: X@r1#0"}]
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert "search_result" not in json.dumps(kw["messages"])


def test_structured_parses_json():
    client = StubClient(response([NS(type="thinking", thinking=""), text_block('{"records": [{"type": "Claim"}]}')]))
    out = ClaudeConnector(client).structured(EXTRACT_SPEC, Prompt("S", "U", schema=SCHEMA))
    assert out.data == {"records": [{"type": "Claim"}]} and out.served_by == "claude-opus-5-5"


def test_structured_truncated_json_is_reported():
    client = StubClient(response([text_block('{"records": [')], stop="max_tokens"))
    out = ClaudeConnector(client).structured(EXTRACT_SPEC, Prompt("S", "U", schema=SCHEMA))
    assert out.data == {} and out.stop_reason == "max_tokens"


def test_estimate_adds_schema_overhead():
    client = StubClient(response([]))
    conn = ClaudeConnector(client)
    assert conn.estimate_input_tokens(EXTRACT_SPEC, Prompt("S", "U", schema=SCHEMA)) == 1234 + len(json.dumps(SCHEMA)) // 3
    assert conn.estimate_input_tokens(ANSWER_SPEC, ANSWER_PROMPT) == 1234
    assert client.count_calls[1]["messages"][0]["content"][0]["type"] == "search_result"


def test_client_created_lazily(monkeypatch):
    import anthropic
    made = []
    monkeypatch.setattr(anthropic, "Anthropic", lambda: made.append(1) or StubClient(response([text_block("ok")])))
    conn = ClaudeConnector()
    assert made == [] and conn.provider == "claude" and conn.hosted is True
    conn.answer(ANSWER_SPEC, ANSWER_PROMPT)
    assert made == [1]
