import pytest

from goldthread.aliases import AliasTable
from goldthread.checks import render_checks_md, run_checks
from goldthread.core import Record
from goldthread.trace import render_trace_md, trace


@pytest.fixture
def aliases(synthetic_pack):
    return AliasTable.from_csv(synthetic_pack.aliases_path)


def rec(store, fragment):
    return next(r for r in store.records() if fragment in r.quote)


def test_trace_from_alias_code(extracted, aliases):
    md = render_trace_md(trace(extracted, aliases, "PDC 10"), [])
    for fragment in ("fuel design limits", "The design meets Criterion 10", "TR-123", "staff finds", "Condition 1:"):
        assert rec(extracted, fragment).id in md
    assert extracted.records("Argument")[0].id in md
    assert "cited, not available in this pack" in md and "(draft, not yet reviewed)" in md
    assert "`SYN-SAR@r2#p1.4`" in md and "<- meets" in md and "-> cites" in md
    assert rec(extracted, "inherent protection").id not in md  # Criterion 11 is not part of this thread


def test_trace_by_record_id_matches_code(extracted, aliases):
    req = rec(extracted, "fuel design limits")
    assert render_trace_md(trace(extracted, aliases, req.id), []) == render_trace_md(trace(extracted, aliases, "Criterion 10"), [])


def test_trace_unknown_code(extracted, aliases):
    assert trace(extracted, aliases, "PDC 99") == []
    assert render_trace_md([], ["A@r1 — Doc A"]).startswith("Not found. Searched:\n- A@r1 — Doc A")


def test_trace_skips_rejected(extracted, aliases):
    bad = rec(extracted, "1700 C")
    extracted.set_review(bad.id, "rejected", "alice", "2026-11-21T00:00:00Z", None, None, bad.flags)
    assert bad.id not in render_trace_md(trace(extracted, aliases, "PDC 10"), [])


def test_trace_shows_flags(extracted, aliases):
    md = render_trace_md(trace(extracted, aliases, "PDC 10"), [])
    assert "⚠ quote_failed: quote not found in passage" in md


def test_coverage_rules(extracted, synthetic_pack):
    report = run_checks(extracted, synthetic_pack.schema)
    assert report.coverage["Requirements with no claim"] == [rec(extracted, "inherent protection").id]
    assert report.coverage["Findings with conditions"] == [rec(extracted, "staff finds").id]
    assert report.coverage["Arguments citing evidence not loaded"] == [extracted.records("Argument")[0].id]
    assert report.coverage["Claims with no argument"] == [rec(extracted, "1700 C").id]
    assert report.superseded_citations == []


def test_superseded_citations(extracted, synthetic_pack):
    old = Record("CLM-old00001", "Claim", {"requirement_code": "PDC 10", "text": "x"}, "SYN-SAR@r1#p1.1",
                 "The fuel temperature limit is 1600 C.", "draft")
    extracted.upsert_record(old)
    assert run_checks(extracted, synthetic_pack.schema).superseded_citations == ["CLM-old00001"]


def test_render_checks_md(extracted, synthetic_pack):
    md = render_checks_md(run_checks(extracted, synthetic_pack.schema))
    assert "Requirements with no claim (1)" in md and "Citations of superseded revisions (0)" in md
