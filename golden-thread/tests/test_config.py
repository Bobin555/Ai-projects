import pytest

from goldthread.config import PackError, load_pack, pack_version, update_register_checksum
from goldthread.core import Budget, ModelSpec


def edit(path, old, new):
    text = path.read_text()
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1))


def test_load_synthetic_pack(synthetic_pack_dir, tmp_path):
    pack = load_pack(synthetic_pack_dir, data_root=tmp_path / "data")
    assert pack.name == "synthetic" and pack.offline is True
    assert pack.models["answer"] == ModelSpec("fake", "fake", "high", 4000)
    assert pack.budget == Budget(1.0, 5.0)
    assert [f"{e.doc_id}@{e.revision}" for e in pack.register] == [
        "SYN-RG1@r1", "SYN-SAR@r1", "SYN-SAR@r2", "SYN-SE@r1"]
    assert pack.register[2].supersedes == "SYN-SAR@r1"
    assert pack.data_dir == tmp_path / "data" / "synthetic"
    assert pack.schema.link_types["meets"].targets == {"Requirement": "code"}


def test_offline_pack_rejects_hosted_provider(synthetic_pack_dir):
    edit(synthetic_pack_dir / "pack.yaml", "answer: {provider: fake", "answer: {provider: claude")
    with pytest.raises(PackError, match="offline pack cannot use hosted provider 'claude' for job 'answer'"):
        load_pack(synthetic_pack_dir)


def test_sensitive_pack_must_be_offline(synthetic_pack_dir):
    p = synthetic_pack_dir / "pack.yaml"
    edit(p, "sensitivity: public", "sensitivity: sensitive")
    edit(p, "offline: true", "offline: false")
    with pytest.raises(PackError, match="sensitive pack must be offline"):
        load_pack(synthetic_pack_dir)


def test_missing_file_named(synthetic_pack_dir):
    (synthetic_pack_dir / "rules.md").unlink()
    with pytest.raises(PackError, match="rules.md"):
        load_pack(synthetic_pack_dir)


def test_unknown_provider(synthetic_pack_dir):
    edit(synthetic_pack_dir / "pack.yaml", "extract: {provider: fake", "extract: {provider: magic")
    with pytest.raises(PackError, match="unknown provider 'magic'"):
        load_pack(synthetic_pack_dir)


def test_bad_doc_id(synthetic_pack_dir):
    edit(synthetic_pack_dir / "register.csv", "SYN-SE,", "ML 123,")
    with pytest.raises(PackError, match="invalid doc_id 'ML 123'"):
        load_pack(synthetic_pack_dir)


def test_duplicate_register_row(synthetic_pack_dir):
    reg = synthetic_pack_dir / "register.csv"
    reg.write_text(reg.read_text() + "SYN-RG1,Duplicate,regulatory_guide,r1,2024-01-15,issued,,,\n")
    with pytest.raises(PackError, match="duplicate register row SYN-RG1@r1"):
        load_pack(synthetic_pack_dir)


def test_supersedes_must_exist(synthetic_pack_dir):
    edit(synthetic_pack_dir / "register.csv", "issued,SYN-SAR@r1", "issued,SYN-XX@r9")
    with pytest.raises(PackError, match="supersedes unknown SYN-XX@r9"):
        load_pack(synthetic_pack_dir)


def test_link_type_unknown_record_type(synthetic_pack_dir):
    edit(synthetic_pack_dir / "records.yaml", "to: {Requirement: code}", "to: {Widget: code}")
    with pytest.raises(PackError, match="unknown record type"):
        load_pack(synthetic_pack_dir)


def test_pack_version_stable_and_changes(synthetic_pack_dir):
    v1 = pack_version(load_pack(synthetic_pack_dir))
    assert v1 == pack_version(load_pack(synthetic_pack_dir))
    assert len(v1) == 12
    rules = synthetic_pack_dir / "rules.md"
    rules.write_text(rules.read_text() + "\n- one more rule\n")
    assert pack_version(load_pack(synthetic_pack_dir)) != v1


def test_update_register_checksum(synthetic_pack_dir):
    reg = synthetic_pack_dir / "register.csv"
    before = reg.read_text().splitlines()
    update_register_checksum(load_pack(synthetic_pack_dir), "SYN-SE", "r1", "ab" * 32)
    after = reg.read_text().splitlines()
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and changed == [4]
    assert after[4].endswith("," + "ab" * 32)
