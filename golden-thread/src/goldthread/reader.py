"""Read a PDF into addressed passages."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Sequence

import pdfplumber

from goldthread.core import DocumentEntry, Passage

HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S)")
MAX_HEADING_CHARS = 100
GAP_FACTOR = 0.6  # a gap larger than this many median line heights starts a new block
SCANNED_MAX_CHARS = 200  # a page this short that is mostly image is treated as scanned
SCANNED_MIN_IMAGE_SHARE = 0.5


def address_of(doc_id: str, revision: str, page: int, n: int) -> str:
    return f"{doc_id}@{revision}#p{page}.{n}"


def heading_depth(line: str) -> int | None:
    """Depth of a line that looks like a numbered heading, or None.

    The word after the number must start with a capital letter, and the line must not end like a sentence or a
    clause, so continuation lines ("1600 degrees C ...") and footers ("3 of 20") are not headings.
    """
    s = line.strip()
    match = HEADING_RE.match(s)
    if not match or len(s) > MAX_HEADING_CHARS or s[-1] in ".,;:" or not match.group(2).isupper():
        return None
    return len(match.group(1).split("."))


@dataclass
class _Line:
    top: float
    bottom: float
    text: str
    size: float
    bold: bool


def _lines(page) -> list[_Line]:
    out = []
    for ln in page.extract_text_lines(return_chars=True):
        chars = ln.get("chars") or []
        sizes = [c.get("size", 0) for c in chars] or [0]
        bold = sum("bold" in str(c.get("fontname", "")).lower() for c in chars) > len(chars) / 2 if chars else False
        out.append(_Line(ln["top"], ln["bottom"], ln["text"], median(sizes), bold))
    return out


def _is_scanned(page) -> bool:
    if len(page.chars) >= SCANNED_MAX_CHARS or not page.images:
        return False
    area = sum(max(0.0, (im["x1"] - im["x0"])) * max(0.0, (im["bottom"] - im["top"])) for im in page.images)
    return area >= SCANNED_MIN_IMAGE_SHARE * page.width * page.height


def read_pdf(path: Path, entry: DocumentEntry, withheld_patterns: Sequence[str] = ()) -> list[Passage]:
    patterns = [re.compile(p, re.DOTALL) for p in withheld_patterns]
    stack: list[tuple[int, str]] = []  # heading path as (depth, text)
    passages: list[Passage] = []

    def heading_path() -> str:
        return " > ".join(text for _, text in stack)

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            if not page.chars:
                passages.append(Passage(address_of(entry.doc_id, entry.revision, page_no, 1),
                                        entry.doc_id, entry.revision, page_no, 1, "", "", "no_text"))
                continue

            events: list[tuple[float, str, object]] = []  # (top, kind, payload)
            text_page = page
            for table in page.find_tables():
                rows = table.extract()
                text = "\n".join(" | ".join((cell or "").strip() for cell in row) for row in rows)
                events.append((table.bbox[1], "table", text))
                text_page = text_page.outside_bbox(table.bbox)
            lines = _lines(text_page)
            heights = [ln.bottom - ln.top for ln in lines]
            gap_limit = GAP_FACTOR * (median(heights) if heights else 10.0)
            body_size = median([ln.size for ln in lines]) if lines else 0.0

            # group consecutive lines into blocks separated by vertical gaps
            blocks: list[list[_Line]] = []
            for ln in sorted(lines, key=lambda x: x.top):
                if blocks and ln.top - blocks[-1][-1].bottom <= gap_limit:
                    blocks[-1].append(ln)
                else:
                    blocks.append([ln])
            events.extend((block[0].top, "block", block) for block in blocks)
            events.sort(key=lambda e: e[0])

            items: list[list[str]] = []  # [kind, heading, text]
            for _, kind, payload in events:
                if kind == "table":
                    items.append(["table", heading_path(), payload])
                    continue
                block: list[_Line] = payload
                first = block[0]
                depth = heading_depth(first.text)
                stands_out = len(block) == 1 or first.bold or first.size > body_size + 0.5
                rest = block
                if depth is not None and stands_out:
                    while stack and stack[-1][0] >= depth:
                        stack.pop()
                    stack.append((depth, first.text.strip()))
                    items.append(["heading", heading_path(), first.text])
                    rest = block[1:]
                if rest:
                    items.append(["text", heading_path(), "\n".join(ln.text for ln in rest)])

            # withheld markers: match across the whole page so wrapped or split redactions are caught
            if patterns:
                joined, spans = "", []
                for i, (kind, _, text) in enumerate(items):
                    if kind in ("text", "table"):
                        spans.append((i, len(joined), len(joined) + len(text)))
                        joined += text + "\n\n"
                for pattern in patterns:
                    for m in pattern.finditer(joined):
                        for i, start, end in spans:
                            if start < m.end() and m.start() < end:
                                items[i][0] = "withheld"
            if _is_scanned(page):
                items.append(["no_text", "", ""])

            for n, (kind, heading, text) in enumerate(items, start=1):
                passages.append(Passage(address_of(entry.doc_id, entry.revision, page_no, n),
                                        entry.doc_id, entry.revision, page_no, n, heading, text, kind))
    return passages
