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
def rg1(synthetic_pack) -> list[Passage]:
    from goldthread.reader import read_pdf
    return read_pdf(pdf_path(synthetic_pack, "SYN-RG1@r1"), entry_of(synthetic_pack, "SYN-RG1@r1"))
