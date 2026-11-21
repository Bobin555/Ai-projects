import pytest

from goldthread.aliases import AliasTable
from goldthread.audit import AuditLog
from goldthread.budget import BudgetGuard, Ledger, Price, PriceTable
from goldthread.core import Budget, Passage, Record
from goldthread.extractor import extract_pack, make_chunks
from goldthread.linker import link_records
from goldthread.models import get_connector
from goldthread.models.fake import FakeConnector
from goldthread.records import extraction_schema, record_id


@pytest.fixture
def ctx(synthetic_pack, store, tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    return dict(pack=synthetic_pack, store=store, ledger=ledger, audit=AuditLog(tmp_path / "audit.jsonl"),
                aliases=AliasTable.from_csv(synthetic_pack.aliases_path),
                connector=get_connector("fake", pack=synthetic_pack))


def extract(ctx, run_id="run-1", connector=None, guard=None, **kw):
    pack = ctx["pack"]
    guard = guard or BudgetGuard(pack.budget, ctx["ledger"], PriceTable.load(), run_id)
    return extract_pack(pack, ctx["store"], connector or ctx["connector"], pack.models["extract"], guard,
                        ctx["audit"], run_id, **kw)


def by_quote(store, fragment):
    return next(r for r in store.records() if fragment in r.quote)


def P(doc, n, text, heading="1 A"):
    return Passage(f"{doc}@r1#p1.{n}", doc, "r1", 1, n, heading, text, "text")


def test_make_chunks_never_mix_documents_and_respect_size():
    passages = [P("A", 1, "x" * 40), P("A", 2, "y" * 40), P("A", 3, "z" * 40, "2 B"),
                P("B", 1, "w" * 40), Passage("B@r1#p2.1", "B", "r1", 2, 1, "", "", "no_text")]
    chunks = make_chunks(passages, max_chars=60)
    assert [c.id for c in chunks] == ["A@r1#0", "A@r1#1", "A@r1#2", "B@r1#0"]
    assert all(len({p.doc_id for p in c.passages}) == 1 for c in chunks)
    assert all(sum(len(p.text) for p in c.passages) <= 60 for c in chunks)
    assert chunks[2].heading == "2 B"


def test_extraction_schema_enums(synthetic_pack):
    schema = extraction_schema(synthetic_pack.schema, ["Requirement"], ["A@r1#p1.1", "A@r1#p1.2"])
    item = schema["properties"]["records"]["items"]
    assert item["properties"]["type"]["enum"] == ["Requirement"]
    assert item["properties"]["address"]["enum"] == ["A@r1#p1.1", "A@r1#p1.2"]
    assert set(item["properties"]["fields"]["items"]["properties"]["name"]["enum"]) == {"code", "text"}
    for obj in (schema, item, item["properties"]["fields"]["items"]):
        assert obj["additionalProperties"] is False and set(obj["required"]) == set(obj["properties"])


def test_extract_creates_drafts_and_flags_bad_quote(ctx):
    report = extract(ctx)
    records = ctx["store"].records()
    assert report.records_new == len(records) == 8 and report.chunks_done == report.chunks_total == 5
    assert all(r.status == "draft" for r in records)
    bad = by_quote(ctx["store"], "1700 C")
    assert bad.flags == ("quote_failed: quote not found in passage",)
    assert all(r.flags == () for r in records if r.id != bad.id)
    assert report.records_flagged == 1
    claim = by_quote(ctx["store"], "The design meets Criterion 10")
    assert claim.fields["key"] == "k1" and claim.chunk_id == "SYN-SAR@r2#0" and claim.extracted_by == "fake"


def test_missing_required_field_flagged(ctx):
    conn = FakeConnector(extractions={"SYN-SE@r1#0": [{
        "type": "Finding", "key": "k1", "address": "SYN-SE@r1#p1.2",
        "quote": "The staff finds the fuel design acceptable", "fields": [{"name": "subject_code", "value": "PDC 10"}]}]})
    extract(ctx, connector=conn, only_docs=["SYN-SE"])
    assert by_quote(ctx["store"], "staff finds").flags == ("missing_field: conclusion",)


def test_ids_stable_and_review_preserved(ctx):
    extract(ctx)
    target = by_quote(ctx["store"], "The design meets Criterion 10")
    ctx["store"].set_review(target.id, "verified", "alice", "2026-11-21T00:00:00Z", None, None, ())
    report = extract(ctx, run_id="run-2")
    assert ctx["store"].record(target.id).status == "verified" and report.records_new == 0
    assert len(ctx["store"].records()) == 8


def test_extract_budget_stop_and_resume(ctx):
    pricey = PriceTable({"fake": Price(1000, 0, 0, 0)})
    conn = get_connector("fake", pack=ctx["pack"])
    conn.hosted = True
    tight = BudgetGuard(Budget(0.5, 100), ctx["ledger"], pricey, "run-b")
    first = extract(ctx, run_id="run-b", connector=conn, guard=tight)
    assert first.stopped == "budget: run limit" and first.remaining_chunks
    assert 0 < first.chunks_done < first.chunks_total
    roomy = BudgetGuard(Budget(100, 100), ctx["ledger"], pricey, "run-b")
    second = extract(ctx, run_id="run-b", connector=conn, guard=roomy, resume=True)
    assert second.stopped is None and second.remaining_chunks == [] and second.chunks_done == second.chunks_total
    assert len(ctx["store"].records()) == 8


def test_only_docs_filter(ctx):
    report = extract(ctx, only_docs=["SYN-SE"])
    assert report.chunks_total == 1 and {r.type for r in ctx["store"].records()} == {"Finding", "Condition"}


def test_linker_code_scope_uses_aliases(ctx):
    extract(ctx)
    link_records(ctx["store"], ctx["pack"].schema, ctx["aliases"])
    req = by_quote(ctx["store"], "fuel design limits")
    claim = by_quote(ctx["store"], "The design meets Criterion 10")
    finding = by_quote(ctx["store"], "staff finds")
    links = ctx["store"].links(dst=req.id)
    assert any(l.src == claim.id and l.link_type == "meets" for l in links)
    assert any(l.src == finding.id and l.link_type == "evaluates" for l in links)


def test_linker_chunk_scope_and_reverse(ctx):
    extract(ctx)
    link_records(ctx["store"], ctx["pack"].schema, ctx["aliases"])
    argument = ctx["store"].records("Argument")[0]  # its quote is also inside the claim's quote
    evidence = by_quote(ctx["store"], "TR-123")
    condition = by_quote(ctx["store"], "Condition 1:")
    finding = by_quote(ctx["store"], "staff finds")
    assert ctx["store"].links(src=argument.id, link_type="cites")[0].dst == evidence.id
    assert ctx["store"].links(src=condition.id, link_type="limits")[0].dst == finding.id
    claim = by_quote(ctx["store"], "The design meets Criterion 10")
    assert ctx["store"].links(src=argument.id, link_type="supports")[0].dst == claim.id


def test_unresolved_links_reported(ctx):
    extract(ctx)
    rt = ctx["pack"].schema.record_types["Claim"]
    orphan = Record(record_id(rt, "SYN-SAR@r2#p1.2", "The fuel temperature limit is 1650 C."), "Claim",
                    {"key": "k9", "requirement_code": "PDC 99", "text": "x"}, "SYN-SAR@r2#p1.2",
                    "The fuel temperature limit is 1650 C.", "draft", chunk_id="SYN-SAR@r2#0")
    ctx["store"].upsert_record(orphan)
    report = link_records(ctx["store"], ctx["pack"].schema, ctx["aliases"])
    assert f"{orphan.id}.requirement_code=PDC 99" in report.unresolved
    assert report.created > 0
