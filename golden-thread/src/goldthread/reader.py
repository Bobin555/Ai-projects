"""Read a PDF into addressed passages."""
from __future__ import annotations

import re
from pathlib import Path
from statistics import median
from typing import Sequence

import pdfplumber

from goldthread.core import DocumentEntry, Passage

HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
MAX_HEADING_CHARS = 100
GAP_FACTOR = 0.6  # a gap larger than this many median line heights starts a new passage


def address_of(doc_id: str, revision: str, page: int, n: int) -> str:
    return f"{doc_id}@{revision}#p{page}.{n}"


def heading_depth(line: str) -> int | None:
    """Depth of a numbered heading line, or None if the line is not a heading."""
    s = line.strip()
    match = HEADING_RE.match(s)
    if not match or len(s) > MAX_HEADING_CHARS or s.endswith("."):
        return None
    return len(match.group(1).split("."))


def read_pdf(path: Path, entry: DocumentEntry, withheld_patterns: Sequence[str] = ()) -> list[Passage]:
    patterns = [re.compile(p) for p in withheld_patterns]
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

            events: list[tuple[float, float, str, str]] = []  # (top, bottom, kind, text)
            text_page = page
            for table in page.find_tables():
                rows = table.extract()
                text = "\n".join(" | ".join((cell or "").strip() for cell in row) for row in rows)
                events.append((table.bbox[1], table.bbox[3], "table", text))
                text_page = text_page.outside_bbox(table.bbox)
            lines = text_page.extract_text_lines(return_chars=False)
            events.extend((ln["top"], ln["bottom"], "line", ln["text"]) for ln in lines)
            events.sort(key=lambda e: e[0])
            heights = [ln["bottom"] - ln["top"] for ln in lines]
            gap_limit = GAP_FACTOR * (median(heights) if heights else 10.0)

            items: list[tuple[str, str, str]] = []  # (kind, heading, text)
            current: list[str] = []
            prev_bottom: float | None = None

            def flush() -> None:
                if current:
                    items.append(("text", heading_path(), "\n".join(current)))
                    current.clear()

            for top, bottom, kind, text in events:
                if kind == "table":
                    flush()
                    items.append(("table", heading_path(), text))
                elif (depth := heading_depth(text)) is not None:
                    flush()
                    while stack and stack[-1][0] >= depth:
                        stack.pop()
                    stack.append((depth, text.strip()))
                else:
                    if current and prev_bottom is not None and top - prev_bottom > gap_limit:
                        flush()
                    current.append(text)
                prev_bottom = bottom
            flush()

            for n, (kind, heading, text) in enumerate(items, start=1):
                if kind == "text" and any(p.search(text) for p in patterns):
                    kind = "withheld"
                passages.append(Passage(address_of(entry.doc_id, entry.revision, page_no, n),
                                        entry.doc_id, entry.revision, page_no, n, heading, text, kind))
    return passages
