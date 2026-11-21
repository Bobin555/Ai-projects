"""Regression tests from the final review: non-PDF downloads and cache overwrites (I5), review sheet edits and
encoding (I9, M7 part), where data is written (I10), network guard gaps (M2)."""
import hashlib
import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

import goldthread.cli as cli
from goldthread.config import load_pack, update_register_checksum
from goldthread.fetch import fetch_pack
from goldthread.ingest import ingest_pack, source_path
from goldthread.netguard import NetworkBlocked, no_network
from goldthread.review import export_review, import_review
from goldthread.store import Store

from conftest import entry_of
from test_fetch import load, never, online_pack_dir, write_register  # noqa: F401  (fixture re-used)
from test_review import NOW, read_sheet, row_for, write_sheet

PDF = b"%PDF-1.7\n% register copy\n"
USERS = b"%PDF-1.7\n% the user's own copy\n"
HTML = b"<!DOCTYPE html><html><body>Document not available</body></html>"


# --- I5: fetch never saves or pins a non-PDF, and never overwrites a cached file without keeping it -------------

def test_download_that_is_not_a_pdf_is_rejected_and_not_pinned(online_pack_dir, tmp_path):
    pack = load(online_pack_dir, tmp_path)
    report = fetch_pack(pack, opener=lambda url: HTML)
    assert report.downloaded == [] and report.recorded_checksums == []
    assert len(report.failed) == 1 and report.failed[0].startswith("DOC-A@r1: download is not a PDF")
    assert not (pack.data_dir / "cache" / "DOC-A@r1.pdf").exists()
    assert load(online_pack_dir, tmp_path).register[0].sha256 == ""


def test_cached_non_pdf_is_not_pinned_and_is_kept_aside_when_replaced(online_pack_dir, tmp_path):
    pack = load(online_pack_dir, tmp_path)
    cache = pack.data_dir / "cache"
    cache.mkdir(parents=True)
    (cache / "DOC-A@r1.pdf").write_bytes(HTML)
    report = fetch_pack(pack, opener=lambda url: PDF)
    assert report.downloaded == ["DOC-A@r1"] and (cache / "DOC-A@r1.pdf").read_bytes() == PDF
    assert load(online_pack_dir, tmp_path).register[0].sha256 == hashlib.sha256(PDF).hexdigest()
    assert [p.read_bytes() for p in (cache / "quarantine").iterdir()] == [HTML]
    assert len(report.quarantined) == 1 and "is not a PDF" in report.quarantined[0]


def test_cached_file_not_matching_register_is_quarantined_not_overwritten(online_pack_dir, tmp_path):
    write_register(online_pack_dir, sha=hashlib.sha256(PDF).hexdigest())
    pack = load(online_pack_dir, tmp_path)
    cache = pack.data_dir / "cache"
    cache.mkdir(parents=True)
    (cache / "DOC-A@r1.pdf").write_bytes(USERS)
    report = fetch_pack(pack, opener=lambda url: PDF)
    assert report.downloaded == ["DOC-A@r1"] and (cache / "DOC-A@r1.pdf").read_bytes() == PDF
    assert [p.read_bytes() for p in (cache / "quarantine").glob("DOC-A@r1.*.pdf")] == [USERS]
    assert "does not match the register checksum" in report.quarantined[0]


def test_cached_file_left_in_place_when_no_good_replacement(online_pack_dir, tmp_path):
    # The review's case: the register pinned an HTML page; the user then saved the real PDF into the cache.
    write_register(online_pack_dir, sha=hashlib.sha256(HTML).hexdigest())
    pack = load(online_pack_dir, tmp_path)
    cache = pack.data_dir / "cache"
    cache.mkdir(parents=True)
    (cache / "DOC-A@r1.pdf").write_bytes(USERS)
    report = fetch_pack(pack, opener=lambda url: HTML)
    assert (cache / "DOC-A@r1.pdf").read_bytes() == USERS and report.downloaded == []
    assert any("left in place" in f for f in report.failed)


def test_cached_non_pdf_matching_a_pinned_checksum_is_reported(online_pack_dir, tmp_path):
    write_register(online_pack_dir, sha=hashlib.sha256(HTML).hexdigest())
    pack = load(online_pack_dir, tmp_path)
    (pack.data_dir / "cache").mkdir(parents=True)
    (pack.data_dir / "cache" / "DOC-A@r1.pdf").write_bytes(HTML)
    report = fetch_pack(pack, opener=never)
    assert report.already_present == [] and "register checksum is wrong" in report.failed[0]


def test_ingest_skips_an_unreadable_pdf_and_continues(synthetic_pack, tmp_path):
    entry = entry_of(synthetic_pack, "SYN-SE@r1")
    path = source_path(synthetic_pack, entry)
    path.write_bytes(b"%PDF-1.4 truncated")
    update_register_checksum(synthetic_pack, entry.doc_id, entry.revision, hashlib.sha256(path.read_bytes()).hexdigest())
    pack = load_pack(synthetic_pack.root, data_root=tmp_path / "data")
    report = ingest_pack(pack, Store(tmp_path / "s.sqlite3"))
    assert report.documents == 3
    assert len(report.skipped) == 1 and report.skipped[0].startswith("SYN-SE@r1: unreadable PDF (")


# --- I9 and M7 part: edits in the sheet are applied or refused, never silently dropped ----------------------------

def edited_sheet(store, tmp_path, fragment, decision, **cells):
    path = tmp_path / "sheet.csv"
    export_review(store, path)
    columns, rows = read_sheet(path)
    row = row_for(rows, fragment)
    row.update(decision=decision, **cells)
    write_sheet(path, columns, rows)
    return path, row


def claim_fields(store, **changes):
    claim = next(r for r in store.records("Claim") if "The design meets" in r.quote)
    return json.dumps({**claim.fields, **changes})


def test_fields_json_edit_applied_under_corrected(extracted, synthetic_pack, tmp_path):
    path, row = edited_sheet(extracted, tmp_path, "The design meets", "corrected",
                             fields_json=claim_fields(extracted, requirement_code="PDC 11"))
    report = import_review(extracted, path, "J. Smith", synthetic_pack.schema, now=NOW)
    rec = extracted.record(row["id"])
    assert report.applied == 1 and rec.status == "corrected" and rec.fields["requirement_code"] == "PDC 11"


def test_quote_edit_under_verified_is_refused(extracted, synthetic_pack, tmp_path):
    path, row = edited_sheet(extracted, tmp_path, "TR-123", "verified", quote="Fuel performance is confirmed.")
    report = import_review(extracted, path, "alice", synthetic_pack.schema, now=NOW)
    assert report.applied == 0 and len(report.rejected_rows) == 1
    assert "edited; use decision 'corrected'" in report.rejected_rows[0]
    assert extracted.record(row["id"]).status == "draft"


def test_invalid_fields_json_is_refused(extracted, synthetic_pack, tmp_path):
    path, row = edited_sheet(extracted, tmp_path, "The design meets", "corrected", fields_json="{not json")
    report = import_review(extracted, path, "alice", synthetic_pack.schema, now=NOW)
    assert "invalid fields_json" in report.rejected_rows[0] and extracted.record(row["id"]).status == "draft"


def test_misspelt_field_name_is_refused(extracted, synthetic_pack, tmp_path):
    path, row = edited_sheet(extracted, tmp_path, "The design meets", "corrected",
                             corrected_fields_json=json.dumps({"requirment_code": "PDC 11"}))
    report = import_review(extracted, path, "alice", synthetic_pack.schema, now=NOW)
    assert report.rejected_rows == [f"row {_row_number(path, row['id'])}: corrected_fields_json has unknown fields: "
                                    "requirment_code"]
    assert extracted.record(row["id"]).status == "draft"


def _row_number(path, record_id):
    return 2 + [r["id"] for r in read_sheet(path)[1]].index(record_id)


def test_missing_required_field_keeps_the_record_draft(extracted, synthetic_pack, tmp_path):
    path, row = edited_sheet(extracted, tmp_path, "The design meets", "corrected",
                             corrected_fields_json=json.dumps({"text": ""}))
    report = import_review(extracted, path, "alice", synthetic_pack.schema, now=NOW)
    rec = extracted.record(row["id"])
    assert report.applied == 0 and report.missing_fields == [rec.id]
    assert rec.status == "draft" and "missing_field: text" in rec.flags


def test_sheet_that_is_not_utf8_changes_nothing(extracted, synthetic_pack, tmp_path):
    path = tmp_path / "sheet.csv"
    export_review(extracted, path)
    columns, rows = read_sheet(path)
    rows[0].update(decision="rejected", note="x" * 10000)  # pushes the bad byte past the reader's first buffer
    rows[-1]["note"] = "café"
    with path.open("w", encoding="cp1252", newline="") as fh:  # what Excel's plain "CSV" save writes
        import csv
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="not UTF-8"):
        import_review(extracted, path, "alice", synthetic_pack.schema, now=NOW)
    assert extracted.record(rows[0]["id"]).status == "draft"


# --- I10: data is written next to the packs folder, and a data folder git would commit is warned about -----------

def test_data_root_defaults_next_to_the_packs_folder(synthetic_pack_dir, tmp_path, monkeypatch):
    project = tmp_path / "project"
    shutil.copytree(synthetic_pack_dir, project / "packs" / "syn")
    monkeypatch.delenv("GT_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert load_pack(project / "packs" / "syn").data_dir == project / "data" / "synthetic"


def test_gitignore_covers_offline_pack_sources():
    root = Path(__file__).resolve().parents[1]
    assert subprocess.run(["git", "check-ignore", "-q", "packs/any-pack/source/doc.pdf"], cwd=root).returncode == 0


def test_cli_warns_when_data_would_be_committed(synthetic_pack_dir, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    shutil.copytree(synthetic_pack_dir, repo / "packs" / "syn")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.delenv("GT_DATA_DIR", raising=False)
    cli.main(["--pack", str(repo / "packs" / "syn"), "spend"])
    err = capsys.readouterr().err
    assert "warning:" in err and str(repo / "data" / "synthetic") in err and "not git-ignored" in err
    assert str(repo / "packs" / "syn" / "source") in err
    (repo / ".gitignore").write_text("data/\npacks/*/source/\n")
    cli.main(["--pack", str(repo / "packs" / "syn"), "spend"])
    assert "not git-ignored" not in capsys.readouterr().err


# --- M2: the offline guard also blocks name lookups and unconnected UDP --------------------------------------------

def test_no_network_blocks_name_lookups_and_udp():
    saved = socket.gethostbyname
    with no_network():
        for lookup in (socket.gethostbyname, socket.gethostbyname_ex, socket.gethostbyaddr):
            with pytest.raises(NetworkBlocked):
                lookup("localhost")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            with pytest.raises(NetworkBlocked):
                udp.sendto(b"x", ("127.0.0.1", 9))
            with pytest.raises(NetworkBlocked):
                udp.sendmsg([b"x"], [], 0, ("127.0.0.1", 9))
    assert socket.gethostbyname is saved
