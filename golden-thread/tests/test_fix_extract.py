"""Regression tests from the final review, re-graded: a failed extraction chunk is not counted as extracted and can be
retried alone; documents that cannot be extracted are named (M10)."""
import re
from dataclasses import replace

import yaml

import goldthread.cli as cli
from goldthread.audit import AuditLog
from goldthread.budget import BudgetGuard, Ledger, PriceTable
from goldthread.config import load_pack
from goldthread.extractor import extract_pack, extraction_status
from goldthread.models.fake import FakeConnector
from goldthread.store import Store


class FailOnce(FakeConnector):
    """Cuts the first reply for one chunk short, as a max_tokens stop does."""

    def __init__(self, failing, **kw):
        super().__init__(**kw)
        self.failing, self.failed = failing, False

    def structured(self, spec, prompt):
        raw = super().structured(spec, prompt)
        if prompt.user_text.startswith(f"CHUNK: {self.failing}\n") and not self.failed:
            self.failed = True
            return replace(raw, data={}, stop_reason="max_tokens")
        return raw


def fail_once(pack, chunk="SYN-SE@r1#0"):
    extractions = yaml.safe_load((pack.root / "fake_extractions.yaml").read_text(encoding="utf-8"))
    return FailOnce(chunk, extractions=extractions)


def extract(pack, store, conn, tmp_path, run_id="run-f", **kw):
    guard = BudgetGuard(pack.budget, Ledger(tmp_path / "l.sqlite3"), PriceTable.load(), run_id)
    return extract_pack(pack, store, conn, pack.models["extract"], guard, AuditLog(tmp_path / "a.jsonl"), run_id, **kw)


def test_failed_chunk_is_not_counted_as_extracted_and_resume_retries_it(synthetic_pack, store, tmp_path):
    conn = fail_once(synthetic_pack)
    first = extract(synthetic_pack, store, conn, tmp_path)
    assert first.failed_chunks == ["SYN-SE@r1#0: max_tokens"] and first.chunks_done == first.chunks_total - 1
    assert extraction_status(synthetic_pack, store)["SYN-SE@r1"] == (0, 1) and not store.records("Finding")
    second = extract(synthetic_pack, store, conn, tmp_path, resume=True)
    assert second.failed_chunks == [] and second.chunks_done == second.chunks_total
    assert extraction_status(synthetic_pack, store)["SYN-SE@r1"] == (1, 1) and store.records("Finding")


def cli_run(pack, tmp_path, capsys, *args):
    code = cli.main(["--pack", str(pack.root), "--data-root", str(tmp_path / "data"), *args])
    out, err = capsys.readouterr()
    return code, out + err


def test_cli_extract_with_failed_chunks_exits_1_with_resume_hint(synthetic_pack, tmp_path, capsys, monkeypatch):
    cli_run(synthetic_pack, tmp_path, capsys, "ingest")
    conn = fail_once(synthetic_pack)
    monkeypatch.setattr(cli, "get_connector", lambda provider, pack=None, client=None: conn)
    code, text = cli_run(synthetic_pack, tmp_path, capsys, "extract")
    assert code == 1 and "SYN-SE@r1#0: max_tokens" in text and re.search(r"extract --resume \d{8}T\d{6}Z-\w+", text)


def add_unrecipied_document(pack, tmp_path):
    register = pack.root / "register.csv"
    register.write_text(register.read_text(encoding="utf-8") + "SYN-NEW,New document,unknown_layout,r1,2026-01-01,"
                        "issued,,,\n", encoding="utf-8")
    return load_pack(pack.root, data_root=tmp_path / "data")


def test_extract_names_documents_it_cannot_extract(synthetic_pack, tmp_path):
    pack = add_unrecipied_document(synthetic_pack, tmp_path)
    report = extract(pack, Store(tmp_path / "empty.sqlite3"), FakeConnector(), tmp_path, run_id="run-s")
    assert report.skipped_documents == ["SYN-RG1@r1: not ingested", "SYN-SAR@r2: not ingested",
                                        "SYN-SE@r1: not ingested", "SYN-NEW@r1: no layout recipe 'unknown_layout'"]


def test_trace_lists_documents_without_a_layout_recipe(synthetic_pack, tmp_path, capsys):
    pack = add_unrecipied_document(synthetic_pack, tmp_path)
    cli_run(pack, tmp_path, capsys, "ingest")
    cli_run(pack, tmp_path, capsys, "extract")
    _, text = cli_run(pack, tmp_path, capsys, "trace", "PDC 10")
    assert "SYN-NEW@r1" in text.partition("Not yet extracted:")[2] and "no layout recipe" in text
