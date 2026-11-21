import pytest

from goldthread.config import PackError, load_pack
from goldthread.core import ModelSpec, Passage
from goldthread.models import get_connector
from goldthread.models.base import NOT_FOUND, Prompt, RawBlock, RawCitation
from goldthread.models.fake import FakeConnector

SPEC = ModelSpec("fake", "fake", "high", 4000)
P1 = Passage("D@r1#p1.1", "D", "r1", 1, 1, "1 Intro", "First sentence here. Second sentence.", "text")
P2 = Passage("D@r1#p1.2", "D", "r1", 1, 2, "1 Intro", "Another one! More text.", "text")
P3 = Passage("D@r1#p1.3", "D", "r1", 1, 3, "1 Intro", "a | b", "table")
JUDGE_SCHEMA = {"type": "object", "properties": {"verdict": {"enum": ["yes", "partial", "no"]},
                                                 "reason": {"type": "string"}}}


def test_default_answer_cites_first_sentence():
    ans = FakeConnector().answer(SPEC, Prompt("sys", "q?", (P1, P2)))
    assert [b.text for b in ans.blocks] == ["First sentence here.", "Another one!"]
    assert ans.blocks[0].citations == (RawCitation("D@r1#p1.1", "First sentence here."),)
    assert ans.blocks[1].citations == (RawCitation("D@r1#p1.2", "Another one!"),)
    assert (ans.stop_reason, ans.served_by, ans.fallback) == ("end_turn", "fake", False)
    assert ans.usage.input_tokens > 0 and ans.usage.output_tokens > 0


def test_default_answer_skips_non_text_and_stops_at_two():
    extra = Passage("D@r1#p1.4", "D", "r1", 1, 4, "", "Third text passage.", "text")
    ans = FakeConnector().answer(SPEC, Prompt("sys", "q?", (P3, P1, P2, extra)))
    assert [b.citations[0].address for b in ans.blocks] == ["D@r1#p1.1", "D@r1#p1.2"]


def test_script_not_found_and_refuse():
    fc = FakeConnector(script={"q1": "NOT_FOUND", "q2": "REFUSE", "q3": [RawBlock("x", ())]})
    assert fc.answer(SPEC, Prompt("s", "q1", (P1,))).blocks == (RawBlock(NOT_FOUND, ()),)
    refused = fc.answer(SPEC, Prompt("s", "q2", (P1,)))
    assert refused.stop_reason == "refusal" and refused.blocks == ()
    assert fc.answer(SPEC, Prompt("s", "q3", (P1,))).blocks == (RawBlock("x", ()),)


def test_structured_extraction_by_chunk():
    fc = FakeConnector(extractions={"X@r1#0": [{"type": "Requirement"}]})
    schema = {"type": "object", "properties": {"records": {"type": "array"}}}
    out = fc.structured(SPEC, Prompt("s", "CHUNK: X@r1#0\nDOCUMENT: Doc", schema=schema))
    assert out.data == {"records": [{"type": "Requirement"}]}
    assert fc.structured(SPEC, Prompt("s", "CHUNK: Y@r1#0\n", schema=schema)).data == {"records": []}


def test_structured_judge():
    fc = FakeConnector()
    yes = fc.structured(SPEC, Prompt("s", "QUESTION: q\nEXPECTED: 1650\nANSWER: limit is 1650 C", schema=JUDGE_SCHEMA))
    assert yes.data["verdict"] == "yes"
    no = fc.structured(SPEC, Prompt("s", "QUESTION: q\nEXPECTED: 1700\nANSWER: limit is 1650 C", schema=JUDGE_SCHEMA))
    assert no.data["verdict"] == "no"


def test_get_connector_unknown():
    with pytest.raises(PackError, match="unknown provider 'magic'"):
        get_connector("magic")


def test_get_connector_fake_loads_pack_extractions(synthetic_pack_dir, tmp_path):
    (synthetic_pack_dir / "fake_extractions.yaml").write_text("A@r1#0:\n  - {type: Requirement}\n")
    conn = get_connector("fake", pack=load_pack(synthetic_pack_dir, data_root=tmp_path / "data"))
    out = conn.structured(SPEC, Prompt("s", "CHUNK: A@r1#0\n", schema={"properties": {"records": {}}}))
    assert out.data == {"records": [{"type": "Requirement"}]} and conn.hosted is False
