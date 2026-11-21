"""Load a pack's registered documents into the store, checking checksums first."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from goldthread.config import Pack
from goldthread.core import DocumentEntry
from goldthread.reader import read_pdf
from goldthread.store import Store


@dataclass
class IngestReport:
    documents: int = 0
    passages: int = 0
    flagged: list[str] = field(default_factory=list)  # addresses of no_text and withheld passages
    skipped: list[str] = field(default_factory=list)  # "<doc_id>@<rev>: <reason>"


def source_path(pack: Pack, entry: DocumentEntry) -> Path:
    folder = pack.source_dir if pack.offline else pack.data_dir / "cache"
    if folder is None:
        raise ValueError(f"offline pack '{pack.name}' has no source_dir")
    return folder / f"{entry.key}.pdf"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ingest_pack(pack: Pack, store: Store) -> IngestReport:
    report = IngestReport()
    for entry in pack.register:
        path = source_path(pack, entry)
        if not path.is_file():
            report.skipped.append(f"{entry.key}: file missing")
            continue
        if not entry.sha256:
            report.skipped.append(f"{entry.key}: no checksum recorded; run fetch")
            continue
        if sha256_of(path) != entry.sha256:
            report.skipped.append(f"{entry.key}: checksum mismatch")
            continue
        passages = read_pdf(path, entry, pack.withheld_patterns)
        store.upsert_document(entry)
        store.replace_passages(entry.doc_id, entry.revision, passages)
        report.documents += 1
        report.passages += len(passages)
        report.flagged.extend(p.address for p in passages if p.kind in ("no_text", "withheld"))
    return report
