"""Build small text PDFs for tests with reportlab."""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FONT, SIZE, LEADING = "Helvetica", 10, 14
LEFT, TOP_MARGIN, COL_WIDTH, ROW_HEIGHT = 72, 72, 150, 20


@dataclass(frozen=True)
class Heading:
    text: str


@dataclass(frozen=True)
class Para:
    text: str


@dataclass(frozen=True)
class Table:
    rows: list[list[str]]


@dataclass(frozen=True)
class ImageOnly:
    pass


Block = Heading | Para | Table | ImageOnly


def make_pdf(path: Path, pages: list[list[Block]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    width, height = A4
    for blocks in pages:
        y = height - TOP_MARGIN
        for block in blocks:
            if isinstance(block, (Heading, Para)):
                lines = [block.text] if isinstance(block, Heading) else textwrap.wrap(block.text, 90)
                c.setFont(FONT, SIZE)
                for line in lines:
                    c.drawString(LEFT, y, line)
                    y -= LEADING
            elif isinstance(block, Table):
                cols = len(block.rows[0])
                xs = [LEFT + i * COL_WIDTH for i in range(cols + 1)]
                ys = [y + SIZE - j * ROW_HEIGHT for j in range(len(block.rows) + 1)]
                c.grid(xs, ys)
                c.setFont(FONT, SIZE)
                for j, row in enumerate(block.rows):
                    for i, cell in enumerate(row):
                        c.drawString(xs[i] + 4, ys[j] - ROW_HEIGHT + 6, cell)
                y = ys[-1] - LEADING
            elif isinstance(block, ImageOnly):
                c.rect(LEFT, y - 200, 300, 200, stroke=1, fill=1)
                y -= 214
            y -= LEADING  # one line height between blocks
        c.showPage()
    c.save()
