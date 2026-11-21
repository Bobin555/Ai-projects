"""Build small text PDFs for tests with reportlab."""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FONT, BOLD, SIZE, LEADING = "Helvetica", "Helvetica-Bold", 10, 14
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


@dataclass(frozen=True)
class Lines:
    """Lines drawn exactly as given, one per line, with normal leading (no gap between them)."""
    lines: list[str]
    bold_first: bool = False


@dataclass(frozen=True)
class Footer:
    """Text drawn at the bottom of the page, like a page number."""
    text: str


@dataclass(frozen=True)
class Picture:
    """A raster image covering most of the page, as on a scanned page."""
    pass


Block = Heading | Para | Table | ImageOnly | Lines | Footer | Picture


def make_pdf(path: Path, pages: list[list[Block]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    width, height = A4
    for blocks in pages:
        y = height - TOP_MARGIN
        for block in blocks:
            if isinstance(block, Footer):
                c.setFont(FONT, SIZE)
                c.drawString(LEFT, 40, block.text)
                continue
            if isinstance(block, Picture):
                from PIL import Image
                from reportlab.lib.utils import ImageReader
                c.drawImage(ImageReader(Image.new("RGB", (60, 80), (120, 120, 120))), LEFT, 120,
                            width - 2 * LEFT, height - 240)
                continue
            if isinstance(block, (Heading, Para, Lines)):
                if isinstance(block, Heading):
                    lines, bold = [block.text], [True]
                elif isinstance(block, Lines):
                    lines = block.lines
                    bold = [block.bold_first and i == 0 for i in range(len(lines))]
                else:
                    lines = textwrap.wrap(block.text, 90)
                    bold = [False] * len(lines)
                for line, is_bold in zip(lines, bold):
                    c.setFont(BOLD if is_bold else FONT, SIZE)
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
