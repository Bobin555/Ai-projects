"""Regression tests from the final review: reader headings (I2), withheld/scanned flags (I12), prompt headings (I11)."""
from fixtures.pdfs import Footer, Heading, Lines, Para, Picture, Table, make_pdf
from goldthread.core import DocumentEntry
from goldthread.extractor import chunk_user_text, make_chunks
from goldthread.reader import read_pdf

ENTRY = DocumentEntry("DOC", "Doc", "x", "r1", "", "issued", "", "", "")
WITHHELD = [r"\[\[.*?\]\]"]


def read(tmp_path, pages, patterns=()):
    path = tmp_path / "doc.pdf"
    make_pdf(path, pages)
    return read_pdf(path, ENTRY, patterns)


def joined(p):
    return " ".join(p.text.split())


def test_wrapped_line_starting_with_a_number_is_kept(tmp_path):
    ps = read(tmp_path, [[Heading("3 Fuel"), Lines(["The fuel temperature shall not exceed",
                                                     "1600 degrees C during normal operation and",
                                                     "anticipated operational occurrences."])]])
    text = [p for p in ps if p.kind == "text"]
    assert len(text) == 1 and joined(text[0]) == ("The fuel temperature shall not exceed 1600 degrees C during "
                                                  "normal operation and anticipated operational occurrences.")
    assert text[0].heading == "3 Fuel"


def test_wrapped_cfr_citation_line_is_kept(tmp_path):
    ps = read(tmp_path, [[Heading("2 Scope"), Lines(["The application must meet the requirements in",
                                                      "10 CFR 50.34(a)(1) and related provisions."])]])
    assert [joined(p) for p in ps if p.kind == "text"] == [
        "The application must meet the requirements in 10 CFR 50.34(a)(1) and related provisions."]
    assert all(p.heading == "2 Scope" for p in ps)


def test_wrapped_numbered_item_is_text_not_heading(tmp_path):
    ps = read(tmp_path, [[Heading("4 Contents"), Lines(["1. The preliminary safety analysis report shall include",
                                                        "a description of the site and the facility."])]])
    text = [p for p in ps if p.kind == "text"]
    assert len(text) == 1 and joined(text[0]).startswith("1. The preliminary safety analysis report")
    assert text[0].heading == "4 Contents"


def test_page_footer_is_not_a_heading(tmp_path):
    ps = read(tmp_path, [[Heading("2 Design"), Para("First page text."), Footer("3 of 20")],
                         [Para("Next page text.")]])
    assert next(p for p in ps if "Next page text" in p.text).heading == "2 Design"
    assert any("3 of 20" in p.text for p in ps)  # the footer text is kept, not dropped


def test_bold_heading_directly_followed_by_text(tmp_path):
    ps = read(tmp_path, [[Lines(["4.1 Reactor Vessel", "The vessel is made of steel."], bold_first=True)]])
    body = next(p for p in ps if p.kind == "text")
    assert joined(body) == "The vessel is made of steel." and body.heading == "4.1 Reactor Vessel"


def test_heading_lines_are_kept_as_heading_passages(rg1):
    headings = [p.text.strip() for p in rg1 if p.kind == "heading"]
    assert headings == ["1 Scope", "2 Criteria", "2.1 Criterion 10", "2.2 Criterion 11"]


def test_withheld_marker_wrapped_across_lines(tmp_path):
    ps = read(tmp_path, [[Lines(["Burnup data are [[ proprietary", "values ]] and withheld."])]], WITHHELD)
    assert [p.kind for p in ps] == ["withheld"]


def test_withheld_marker_in_table(tmp_path):
    ps = read(tmp_path, [[Table([["Item", "Value"], ["burnup", "[[ withheld ]]"]])]], WITHHELD)
    assert [p.kind for p in ps] == ["withheld"]


def test_withheld_marker_across_passages(tmp_path):
    ps = read(tmp_path, [[Para("Data [[ begins here"), Para("and ends ]] here.")]], WITHHELD)
    assert [p.kind for p in ps] == ["withheld", "withheld"]


def test_mostly_image_page_with_page_number_is_flagged(tmp_path):
    ps = read(tmp_path, [[Picture(), Footer("Page 7")]])
    assert any(p.kind == "no_text" for p in ps)
    assert any("Page 7" in p.text for p in ps)


def test_extraction_prompt_carries_heading_paths(store):
    chunk = next(c for c in make_chunks(store.passages_of("SYN-RG1", "r1")) if c.id == "SYN-RG1@r1#1")
    text = chunk_user_text(chunk, "Synthetic Regulatory Guide 1")
    assert "2 Criteria > 2.1 Criterion 10" in text and "2 Criteria > 2.2 Criterion 11" in text
