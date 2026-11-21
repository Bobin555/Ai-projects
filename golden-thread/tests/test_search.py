import pytest

from goldthread.aliases import AliasTable
from goldthread.search import build_match_expr, find_identifiers, search


@pytest.fixture
def aliases(synthetic_pack):
    return AliasTable.from_csv(synthetic_pack.aliases_path)


def test_alias_find_and_variants(aliases):
    assert aliases.find("Does the design meet Criterion 10?") == ["PDC 10"]
    assert set(aliases.variants("PDC 10")) == {"PDC 10", "Criterion 10", "MHTGR-DC 10"}
    assert aliases.canonical("mhtgr dc 10") == "PDC 10"
    assert aliases.canonical("Criterion 99") is None


def test_alias_word_boundary(aliases):
    assert aliases.find("PDC 100") == []
    assert aliases.find("PDC 1") == []
    assert aliases.find("see 50.34(a).") == ["10 CFR 50.34(a)"]


def test_find_identifiers():
    assert find_identifiers("What does 10 CFR 50.34(a) say, per RG 1.233 and ML24284A012?") == [
        "50.34(a)", "1.233", "ML24284A012"]


def test_build_match_expr(aliases):
    assert build_match_expr("the of and", aliases) == ""
    expr = build_match_expr("How is PDC 10 met?", aliases)
    assert '"criterion 10"' in expr and '"met"' in expr and " OR " in expr


def test_search_uses_aliases(store, aliases):
    hits = search(store, aliases, "How is PDC 10 met?")
    assert any("meets Criterion 10" in h.passage.text for h in hits)


def test_superseded_excluded_by_default(store, aliases):
    hits = search(store, aliases, "fuel temperature limit")
    assert hits and not any(h.passage.address.startswith("SYN-SAR@r1#") for h in hits)
    hits = search(store, aliases, "fuel temperature limit", include_superseded=True)
    assert any(h.passage.address.startswith("SYN-SAR@r1#") for h in hits)


def test_identifier_near_miss_excluded(store, aliases):  # Review Focus 1
    hits = search(store, aliases, "What does 50.34(a) require?")
    assert hits and all("50.34(a)" in h.passage.text for h in hits)
    assert not any("50.34(b)" in h.passage.text for h in hits)


def test_stopwords_only_returns_empty(store, aliases):
    assert search(store, aliases, "the of and") == []


def test_k_limit(store, aliases):
    assert len(search(store, aliases, "fuel", k=1)) == 1


def test_no_text_passages_skipped(store, aliases):
    assert all(h.passage.kind != "no_text" for h in search(store, aliases, "guide criteria reactor"))
