import re

from conftest import entry_of, pdf_path
from goldthread.core import Passage
from goldthread.reader import address_of, read_pdf


def test_address_format():
    assert address_of("ML24284A012", "rev3", 12, 4) == "ML24284A012@rev3#p12.4"


def test_passages_have_address_heading_and_exact_text(rg1):
    p = next(p for p in rg1 if "fuel design limits" in p.text)
    assert re.fullmatch(r"SYN-RG1@r1#p1\.\d+", p.address)
    assert p.heading == "2 Criteria > 2.1 Criterion 10"
    assert " ".join(p.text.split()).startswith("The reactor core shall be designed")
    assert "\n" in p.text  # wrapped lines kept exactly as extracted


def test_heading_path_pops_siblings(rg1):
    p = next(p for p in rg1 if "inherent protection" in p.text)
    assert p.heading == "2 Criteria > 2.2 Criterion 11"


def test_table_passage(rg1):
    t = next(p for p in rg1 if p.kind == "table")
    assert "10 | Reactor design" in t.text and t.page == 2


def test_image_only_page_flagged_no_text(rg1):  # Review Focus 4
    assert [p for p in rg1 if p.page == 3] == [
        Passage("SYN-RG1@r1#p3.1", "SYN-RG1", "r1", 3, 1, "", "", "no_text")]


def test_withheld_marker_passage(synthetic_pack):  # Review Focus 4
    ps = read_pdf(pdf_path(synthetic_pack, "SYN-SAR@r2"),
                  entry_of(synthetic_pack, "SYN-SAR@r2"), [r"\[\[.*?\]\]"])
    w = next(p for p in ps if "[[ proprietary ]]" in p.text)
    assert w.kind == "withheld"


def test_passage_numbers_count_per_page(rg1):
    for page in {p.page for p in rg1}:
        assert [p.n for p in rg1 if p.page == page] == list(range(1, 1 + sum(p.page == page for p in rg1)))
