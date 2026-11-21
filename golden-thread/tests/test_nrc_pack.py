from pathlib import Path

from goldthread.budget import PriceTable, validate_prices
from goldthread.config import load_pack
from goldthread.core import Budget, ModelSpec

PACK = Path(__file__).parents[1] / "packs" / "nrc-xenergy"


def test_nrc_pack_loads_and_validates(tmp_path):
    pack = load_pack(PACK, data_root=tmp_path)
    assert pack.name == "nrc-xenergy" and pack.sensitivity == "public" and pack.offline is False
    assert pack.models["answer"] == ModelSpec("claude", "claude-opus-5-5", "high", 16000)
    assert pack.models["extract"] == ModelSpec("claude", "claude-opus-5-5", "low", 16000)
    assert pack.models["judge"] == ModelSpec("claude", "claude-opus-5-5", "low", 4000)
    assert pack.budget == Budget(20.0, 150.0)
    validate_prices(pack, PriceTable.load())


def test_nrc_pack_schema_and_layouts(tmp_path):
    pack = load_pack(PACK, data_root=tmp_path)
    assert set(pack.schema.record_types) == {"Requirement", "AcceptedMethod", "Claim", "Argument", "EvidenceRef",
                                             "Finding", "Condition"}
    assert set(pack.schema.link_types) == {"meets", "supports", "follows", "cites", "evaluates", "limits"}
    assert set(pack.layouts) == {"cfr_section", "regulatory_guide", "topical_report", "nrc_safety_evaluation",
                                 "psar_chapter"}
    assert {e.layout for e in pack.register} <= set(pack.layouts)


def test_nrc_pack_register_has_confirmed_documents(tmp_path):
    keys = {e.key for e in load_pack(PACK, data_root=tmp_path).register}
    assert {"ML17325A611@rev0", "ML20091L698@rev0", "ML24284A012@final", "ML25094A140@final",
            "ML26295A004@final"} <= keys
