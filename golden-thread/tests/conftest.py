import hashlib
import shutil
from pathlib import Path

import pytest

from fixtures.pdfs import make_pdf
from fixtures.synthetic_docs import DOCS
from goldthread.config import Pack, load_pack, update_register_checksum
from goldthread.core import DocumentEntry, Passage

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def synthetic_pack_dir(tmp_path) -> Path:
    """A writable copy of the synthetic fixture pack."""
    dst = tmp_path / "packs" / "synthetic"
    shutil.copytree(FIXTURES / "packs" / "synthetic", dst)
    return dst


def pdf_path(pack: Pack, key: str) -> Path:
    return pack.source_dir / f"{key}.pdf"


def entry_of(pack: Pack, key: str) -> DocumentEntry:
    return next(e for e in pack.register if e.key == key)


@pytest.fixture
def synthetic_pack(synthetic_pack_dir, tmp_path) -> Pack:
    """The synthetic pack with its PDFs built and their checksums registered."""
    pack = load_pack(synthetic_pack_dir, data_root=tmp_path / "data")
    for key, pages in DOCS.items():
        make_pdf(pdf_path(pack, key), pages)
        doc_id, rev = key.split("@")
        update_register_checksum(pack, doc_id, rev, hashlib.sha256(pdf_path(pack, key).read_bytes()).hexdigest())
    return load_pack(synthetic_pack_dir, data_root=tmp_path / "data")


@pytest.fixture
def store(synthetic_pack, tmp_path):
    """A store holding the ingested synthetic pack."""
    from goldthread.ingest import ingest_pack
    from goldthread.store import Store
    s = Store(tmp_path / "store.sqlite3")
    ingest_pack(synthetic_pack, s)
    return s


@pytest.fixture
def extracted(synthetic_pack, store, tmp_path):
    """The synthetic store with records extracted by the fake connector and linked."""
    from goldthread.aliases import AliasTable
    from goldthread.audit import AuditLog
    from goldthread.budget import BudgetGuard, Ledger, PriceTable
    from goldthread.extractor import extract_pack
    from goldthread.linker import link_records
    from goldthread.models import get_connector
    guard = BudgetGuard(synthetic_pack.budget, Ledger(tmp_path / "ledger.sqlite3"), PriceTable.load(), "run-x")
    extract_pack(synthetic_pack, store, get_connector("fake", pack=synthetic_pack), synthetic_pack.models["extract"],
                 guard, AuditLog(tmp_path / "audit.jsonl"), "run-x")
    link_records(store, synthetic_pack.schema, AliasTable.from_csv(synthetic_pack.aliases_path))
    return store


@pytest.fixture
def rg1(synthetic_pack) -> list[Passage]:
    from goldthread.reader import read_pdf
    return read_pdf(pdf_path(synthetic_pack, "SYN-RG1@r1"), entry_of(synthetic_pack, "SYN-RG1@r1"))
