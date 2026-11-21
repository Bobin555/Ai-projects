from fixtures.synthetic_docs import CRITERION_10
from goldthread.verifier import Verification, normalise, verify_quote


def address_with(store, doc_id, rev, needle):
    return next(p.address for p in store.passages_of(doc_id, rev) if needle in p.text)


def test_exact_quote_passes(store):
    a = address_with(store, "SYN-SAR", "r2", "1650 C")
    assert verify_quote(store, a, "The fuel temperature limit is 1650 C.") == Verification(True)


def test_line_breaks_and_spaces(store):
    a = address_with(store, "SYN-RG1", "r1", "fuel design limits")
    assert "\n" in store.passage(a).text
    assert verify_quote(store, a, CRITERION_10).ok


def test_normalise_hyphenation():
    assert normalise("contain-\nment", True) == "containment"
    assert normalise("pebble-\nbed", False) == "pebble- bed"


def test_curly_quotes_and_dashes():
    assert normalise("the ‘core’ – limit", False) == "the 'core' - limit"
    assert normalise("“fuel” ‑ pebble", False) == '"fuel" - pebble'


def test_quote_not_in_passage(store):
    a = address_with(store, "SYN-SAR", "r2", "1650 C")
    assert verify_quote(store, a, "The fuel temperature limit is 1700 C.") == Verification(
        False, "quote not found in passage")


def test_cross_passage_quote_fails(store):
    a = address_with(store, "SYN-SAR", "r2", "1650 C")
    assert not verify_quote(store, a, "limit is 1650 C. The design meets Criterion 10").ok


def test_superseded_revision_fails(store):
    a = address_with(store, "SYN-SAR", "r1", "1600 C")
    assert verify_quote(store, a, "The fuel temperature limit is 1600 C.") == Verification(
        False, "cited revision is superseded")


def test_unknown_address(store):
    assert verify_quote(store, "NOPE@r1#p1.1", "anything").reason == "unknown address"


def test_empty_quote(store):
    a = address_with(store, "SYN-SAR", "r2", "1650 C")
    assert verify_quote(store, a, "   ").reason == "empty quote"
