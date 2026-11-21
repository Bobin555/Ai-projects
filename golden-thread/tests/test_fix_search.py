"""Regression tests from the final review: numbered terms must not match longer numbers, and stripping an
acronym from the question must not cut words (I1). Uses the real nrc-xenergy alias table."""
from pathlib import Path

import pytest

from goldthread.aliases import AliasTable
from goldthread.core import DocumentEntry, Passage
from goldthread.search import build_match_expr, search
from goldthread.store import Store

NRC_ALIASES = Path(__file__).resolve().parents[1] / "packs" / "nrc-xenergy" / "aliases.csv"
TEXTS = ["The design meets PDC 10 for reactor design.", "PDC 16 requires functional containment.",
         "Criterion 12 covers suppression of reactor power oscillations.",
         "RG 1.232 provides guidance for design criteria.", "Radionuclide release is limited by the fuel."]


@pytest.fixture
def nrc(tmp_path):
    store = Store(tmp_path / "s.sqlite3")
    store.upsert_document(DocumentEntry("DOC-A", "Doc A", "x", "r1", "", "issued", "", "", ""))
    store.replace_passages("DOC-A", "r1", [Passage(f"DOC-A@r1#p1.{n}", "DOC-A", "r1", 1, n, "1 Scope", t, "text")
                                           for n, t in enumerate(TEXTS, 1)])
    return store, AliasTable.from_csv(NRC_ALIASES)


@pytest.mark.parametrize("question", ["Does the design meet PDC 1?", "Is Criterion 1 about reactor design?",
                                      "What does RG 1.23 say about design?"])
def test_numbered_terms_do_not_match_longer_numbers(nrc, question):
    store, aliases = nrc
    assert search(store, aliases, question) == []


def test_acronym_stripping_keeps_whole_words(nrc):
    store, aliases = nrc
    question = "What does the SE say about radionuclide release?"
    expr = build_match_expr(question, aliases)
    assert '"release"' in expr and '"relea"' not in expr
    assert [h.passage.text for h in search(store, aliases, question)] == [TEXTS[4]]


def test_numbered_term_positive_control(nrc):
    store, aliases = nrc
    assert [h.passage.text for h in search(store, aliases, "Does the design meet PDC 10?")] == [TEXTS[0]]
