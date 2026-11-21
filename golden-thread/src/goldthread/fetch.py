"""Download registered documents into the pack's cache, recording or verifying checksums."""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from goldthread.config import Pack, update_register_checksum
from goldthread.ingest import source_path

USER_AGENT = "golden-thread/0.1"


class OfflineError(Exception):
    """Raised when a network operation is attempted for an offline pack."""


@dataclass
class FetchReport:
    downloaded: list[str] = field(default_factory=list)
    recorded_checksums: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # "<doc_id>@<rev>: <reason>"
    quarantined: list[str] = field(default_factory=list)  # cached files moved aside, never deleted: "<key>: <why>"


def is_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF-")


def _quarantine(cache: Path, key: str, data: bytes) -> Path:
    """Keep bytes aside under a name that includes their checksum, so nothing quarantined is ever overwritten."""
    folder = cache / "quarantine"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key}.{hashlib.sha256(data).hexdigest()[:12]}.pdf"
    path.write_bytes(data)
    return path


def http_get(url: str, timeout: float = 60.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_pack(pack: Pack, opener: Callable[[str], bytes] = http_get) -> FetchReport:
    if pack.offline:
        raise OfflineError("offline pack: fetch is disabled")
    report = FetchReport()
    cache = pack.data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for entry in pack.register:
        key, target = entry.key, source_path(pack, entry)
        cached = target.read_bytes() if target.is_file() else None
        problem = ""  # what is wrong with the cached file; it is replaced only by a good download
        if cached is not None:
            present = hashlib.sha256(cached).hexdigest()
            if is_pdf(cached) and entry.sha256 == present:
                report.already_present.append(key)
                continue
            if is_pdf(cached) and not entry.sha256:
                update_register_checksum(pack, entry.doc_id, entry.revision, present)
                report.recorded_checksums.append(key)
                report.already_present.append(key)
                continue
            if entry.sha256 == present:  # the register pinned something that is not a PDF
                report.failed.append(f"{key}: cached file matches the register checksum but is not a PDF; "
                                     "the register checksum is wrong: clear it and run fetch again")
                continue
            problem = "does not match the register checksum" if is_pdf(cached) else "is not a PDF"
        kept = f"{key}: cached file {problem}; left in place" if problem else ""
        if not entry.url:
            report.failed += [f"{key}: no url in register"] + ([kept] if kept else [])
            continue
        try:
            data = opener(entry.url)
        except (urllib.error.URLError, OSError) as exc:
            report.failed += [f"{key}: download failed: {exc}"] + ([kept] if kept else [])
            continue
        if not is_pdf(data):
            report.failed += [f"{key}: download is not a PDF (starts {data[:20]!r}); not saved"] + ([kept] if kept else [])
            continue
        digest = hashlib.sha256(data).hexdigest()
        if entry.sha256 and digest != entry.sha256:
            _quarantine(cache, key, data)
            report.mismatched.append(key)
            if kept:
                report.failed.append(kept)
            continue
        if cached is not None:
            moved = _quarantine(cache, key, cached)
            report.quarantined.append(f"{key}: cached file {problem}; moved to {moved}")
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(data)
        partial.replace(target)
        report.downloaded.append(key)
        if not entry.sha256:
            update_register_checksum(pack, entry.doc_id, entry.revision, digest)
            report.recorded_checksums.append(key)
    return report
