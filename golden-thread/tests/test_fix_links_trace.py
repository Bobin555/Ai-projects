"""Regression tests from the final review: links as derived state (C1, I7), trace re-checks quotes (C2),
record identity (I6), trace scope (I8, M9)."""
import csv
from dataclasses import replace

import pytest

import goldthread.cli as cli
from goldthread.aliases import AliasTable
from goldthread.audit import AuditLog
from goldthread.budget import BudgetGuard, Ledger, PriceTable
from goldthread.checks import run_checks
from goldthread.config import PackError, load_pack
from goldthread.core import Record
from goldthread.extractor import extract_pack, extraction_status
from goldthread.linker import link_records
from goldthread.models.fake import FakeConnector
from goldthread.records import record_id
from goldthread.trace import render_trace_md, trace


@pytest.fixture
def aliases(synthetic_pack):
    return AliasTable.from_csv(synthetic_pack.aliases_path)


def rec(store, fragment):
    return next(r for r in store.records() if fragment in r.quote)


def test_checks_ignore_links_of_rejected_records(extracted, synthetic_pack):  # C1
    for claim in extracted.records("Claim"):
        extracted.set_review(claim.id, "rejected", "r", "t", None, None, claim.flags)
    report = run_checks(extracted, synthetic_pack.schema)
    assert rec(extracted, "fuel design limits").id in report.coverage["Requirements with no claim"]


def test_relink_drops_links_of_rejected_records(extracted, synthetic_pack, aliases):  # C1
    claim = rec(extracted, "The design meets Criterion 10")
    extracted.set_review(claim.id, "rejected", "r", "t", None, None, ())
    link_records(extracted, synthetic_pack.schema, aliases)
    assert not extracted.links(src=claim.id) and not extracted.links(dst=claim.id)


def test_correction_relinks(extracted, synthetic_pack, aliases):  # I7
    claim = rec(extracted, "The design meets Criterion 10")
    extracted.set_review(claim.id, "corrected", "r", "t", {**claim.fields, "requirement_code": "Criterion 11"},
                         None, ())
    link_records(extracted, synthetic_pack.schema, aliases)
    assert claim.id not in render_trace_md(trace(extracted, aliases, "PDC 10"), [])
    assert claim.id in render_trace_md(trace(extracted, aliases, "Criterion 11"), [])


def test_trace_rechecks_quotes(extracted, aliases):  # C2
    claim = rec(extracted, "The design meets Criterion 10")
    extracted.set_review(claim.id, "verified", "r", "t", None, None, ())
    extracted.upsert_document(replace(extracted.document("SYN-SAR", "r2"), status="superseded"))
    md = render_trace_md(trace(extracted, aliases, "PDC 10"), [])
    line = next(line for line in md.splitlines() if claim.id in line)
    assert "⚠ quote check failed: cited revision is superseded" in line


def test_trace_does_not_follow_shared_methods_into_other_requirements(extracted, synthetic_pack, aliases):  # M9
    schema = synthetic_pack.schema
    q_method = "This guide applies to modular reactors."
    method = Record(record_id(schema.record_types["AcceptedMethod"], "SYN-RG1@r1#p1.2", q_method, {"code": "RG-X"}),
                    "AcceptedMethod", {"code": "RG-X", "title": "x"}, "SYN-RG1@r1#p1.2", q_method, "draft")
    extracted.upsert_record(method)
    arg = extracted.records("Argument")[0]
    extracted.set_review(arg.id, "corrected", "r", "t", {**arg.fields, "method_code": "RG-X"}, None, ())
    q = "10 CFR 50.34(a) requires a preliminary safety analysis report."
    c11 = Record(record_id(schema.record_types["Claim"], "SYN-SAR@r2#p2.2", q, {"requirement_code": "Criterion 11"}),
                 "Claim", {"key": "k1", "requirement_code": "Criterion 11", "text": "x"}, "SYN-SAR@r2#p2.2", q,
                 "draft", chunk_id="SYN-SAR@r2#1")
    a11 = Record(record_id(schema.record_types["Argument"], "SYN-SAR@r2#p2.2", "requires a preliminary",
                           {"method_code": "RG-X"}),
                 "Argument", {"key": "k2", "claim_key": "k1", "method_code": "RG-X", "text": "y"}, "SYN-SAR@r2#p2.2",
                 "requires a preliminary", "draft", chunk_id="SYN-SAR@r2#1")
    extracted.upsert_record(c11)
    extracted.upsert_record(a11)
    link_records(extracted, schema, aliases)
    md = render_trace_md(trace(extracted, aliases, "PDC 10"), [])
    assert method.id in md and a11.id not in md and c11.id not in md


def test_two_claims_from_one_sentence_are_both_kept(synthetic_pack, store, tmp_path):  # I6
    q = "The design meets Criterion 10 because the core keeps fuel below the limit."
    claims = [{"type": "Claim", "key": f"k{i}", "address": "SYN-SAR@r2#p1.3", "quote": q,
               "fields": [{"name": "requirement_code", "value": code}, {"name": "text", "value": "t"}]}
              for i, code in ((1, "Criterion 10"), (2, "Criterion 11"))]
    guard = BudgetGuard(synthetic_pack.budget, Ledger(tmp_path / "l.sqlite3"), PriceTable.load(), "run-1")
    extract_pack(synthetic_pack, store, FakeConnector(extractions={"SYN-SAR@r2#0": claims}),
                 synthetic_pack.models["extract"], guard, AuditLog(tmp_path / "a.jsonl"), "run-1",
                 only_docs=["SYN-SAR"])
    assert sorted(r.fields["requirement_code"] for r in store.records("Claim")) == ["Criterion 10", "Criterion 11"]


def test_identity_fields_must_be_fields(synthetic_pack_dir):  # I6
    path = synthetic_pack_dir / "records.yaml"
    path.write_text(path.read_text().replace("identity: [requirement_code]", "identity: [colour]", 1))
    with pytest.raises(PackError, match=r"Claim: identity fields not in fields: \['colour'\]"):
        load_pack(synthetic_pack_dir)


def cli_run(pack, tmp_path, capsys, *args):
    code = cli.main(["--pack", str(pack.root), "--data-root", str(tmp_path / "data"), *args])
    return code, capsys.readouterr().out


def test_trace_not_found_lists_only_extracted_documents(synthetic_pack, tmp_path, capsys):  # I8
    cli_run(synthetic_pack, tmp_path, capsys, "ingest")
    cli_run(synthetic_pack, tmp_path, capsys, "extract", "--docs", "SYN-SE")
    _, out = cli_run(synthetic_pack, tmp_path, capsys, "trace", "Criterion 11")
    searched, marker, not_extracted = out.partition("Not yet extracted:")
    assert marker and "SYN-SE@r1" in searched and "SYN-RG1@r1" not in searched and "SYN-RG1@r1" in not_extracted


def test_extraction_status_counts_chunks_across_runs(synthetic_pack, store):  # I8
    store.mark_chunk_done("run-1", "SYN-SAR@r2#0")
    store.mark_chunk_done("run-2", "SYN-SE@r1#0")
    assert extraction_status(synthetic_pack, store) == {"SYN-RG1@r1": (0, 2), "SYN-SAR@r2": (1, 2), "SYN-SE@r1": (1, 1)}


def test_trace_lists_partly_extracted_documents_as_not_extracted(synthetic_pack, tmp_path, capsys, monkeypatch):  # I8
    cli_run(synthetic_pack, tmp_path, capsys, "ingest")
    cli_run(synthetic_pack, tmp_path, capsys, "extract")
    monkeypatch.setattr(cli, "extraction_status",
                        lambda pack, store: {"SYN-RG1@r1": (2, 2), "SYN-SAR@r2": (1, 2), "SYN-SE@r1": (1, 1)})
    _, out = cli_run(synthetic_pack, tmp_path, capsys, "trace", "PDC 10")
    found, marker, not_extracted = out.partition("Not yet extracted:")
    assert "REQ-" in found and marker and "SYN-SAR@r2" in not_extracted and "partly extracted: 1/2 chunks" in not_extracted


def test_cli_review_import_relinks(synthetic_pack, tmp_path, capsys):  # C1 via the CLI
    cli_run(synthetic_pack, tmp_path, capsys, "ingest")
    cli_run(synthetic_pack, tmp_path, capsys, "extract")
    sheet = tmp_path / "sheet.csv"
    cli_run(synthetic_pack, tmp_path, capsys, "review-export", "--out", str(sheet))
    with sheet.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns, rows = reader.fieldnames, list(reader)
    for row in rows:
        if row["type"] == "Claim":
            row["decision"] = "rejected"
    with sheet.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    cli_run(synthetic_pack, tmp_path, capsys, "review-import", str(sheet), "--reviewer", "r")
    _, out = cli_run(synthetic_pack, tmp_path, capsys, "check")
    assert "Requirements with no claim (2)" in out
