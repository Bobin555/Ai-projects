from conftest import entry_of, pdf_path
from goldthread.config import load_pack, update_register_checksum
from goldthread.ingest import ingest_pack
from goldthread.reader import read_pdf
from goldthread.store import Store


def total_passages(store):
    return sum(len(store.passages_of(e.doc_id, e.revision)) for e in store.documents())


def test_ingest_offline_pack_counts(synthetic_pack, tmp_path):
    report = ingest_pack(synthetic_pack, Store(tmp_path / "s.sqlite3"))
    assert report.documents == 4 and report.skipped == []
    assert "SYN-RG1@r1#p3.1" in report.flagged
    withheld = [a for a in report.flagged if a.startswith("SYN-SAR@r2")]
    assert len(withheld) == 1


def test_passage_roundtrip(synthetic_pack, store):
    passages = read_pdf(pdf_path(synthetic_pack, "SYN-RG1@r1"), entry_of(synthetic_pack, "SYN-RG1@r1"),
                        synthetic_pack.withheld_patterns)
    for p in passages:
        assert store.passage(p.address) == p
    assert store.passages_of("SYN-RG1", "r1") == passages


def test_documents_status_filter(store):
    assert [e.key for e in store.documents(status="issued")] == ["SYN-RG1@r1", "SYN-SAR@r2", "SYN-SE@r1"]
    assert store.document("SYN-SAR", "r1").status == "superseded"


def test_ingest_skips_checksum_mismatch(synthetic_pack, tmp_path):  # Review Focus 3
    with pdf_path(synthetic_pack, "SYN-SE@r1").open("ab") as fh:
        fh.write(b"\0")
    store = Store(tmp_path / "s.sqlite3")
    report = ingest_pack(synthetic_pack, store)
    assert "SYN-SE@r1: checksum mismatch" in report.skipped
    assert store.document("SYN-SE", "r1") is None
    assert report.documents == 3


def test_ingest_skips_missing_checksum(synthetic_pack, tmp_path):
    update_register_checksum(synthetic_pack, "SYN-SE", "r1", "")
    pack = load_pack(synthetic_pack.root, data_root=tmp_path / "data")
    report = ingest_pack(pack, Store(tmp_path / "s.sqlite3"))
    assert report.skipped == ["SYN-SE@r1: no checksum recorded; run fetch"]


def test_ingest_skips_missing_file(synthetic_pack, tmp_path):
    pdf_path(synthetic_pack, "SYN-SE@r1").unlink()
    report = ingest_pack(synthetic_pack, Store(tmp_path / "s.sqlite3"))
    assert report.skipped == ["SYN-SE@r1: file missing"]


def test_reingest_replaces_passages(synthetic_pack, store):
    before = total_passages(store)
    ingest_pack(synthetic_pack, store)
    assert total_passages(store) == before > 0


def test_fts_search_excludes_superseded(store):
    current = [p.address for p, _ in store.fts_search('"fuel temperature limit"', False, 10)]
    assert current and all(a.startswith("SYN-SAR@r2#") for a in current)
    everything = [p.address for p, _ in store.fts_search('"fuel temperature limit"', True, 10)]
    assert any(a.startswith("SYN-SAR@r1#") for a in everything)
