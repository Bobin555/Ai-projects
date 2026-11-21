import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def synthetic_pack_dir(tmp_path) -> Path:
    """A writable copy of the synthetic fixture pack."""
    dst = tmp_path / "packs" / "synthetic"
    shutil.copytree(FIXTURES / "packs" / "synthetic", dst)
    return dst
