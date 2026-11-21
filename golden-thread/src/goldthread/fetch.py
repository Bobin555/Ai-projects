"""Download registered documents into the pack's cache, recording or verifying checksums."""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from goldthread.config import Pack, update_register_checksum
from goldthread.ingest import sha256_of, source_path

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
        if target.is_file():
            present = sha256_of(target)
            if entry.sha256 == present:
                report.already_present.append(key)
                continue
            if not entry.sha256:
                update_register_checksum(pack, entry.doc_id, entry.revision, present)
                report.recorded_checksums.append(key)
                report.already_present.append(key)
                continue
        if not entry.url:
            report.failed.append(f"{key}: no url in register")
            continue
        try:
            data = opener(entry.url)
        except (urllib.error.URLError, OSError) as exc:
            report.failed.append(f"{key}: download failed: {exc}")
            continue
        digest = hashlib.sha256(data).hexdigest()
        if entry.sha256 and digest != entry.sha256:
            quarantine = cache / "quarantine"
            quarantine.mkdir(exist_ok=True)
            (quarantine / target.name).write_bytes(data)
            report.mismatched.append(key)
            continue
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(data)
        partial.replace(target)
        report.downloaded.append(key)
        if not entry.sha256:
            update_register_checksum(pack, entry.doc_id, entry.revision, digest)
            report.recorded_checksums.append(key)
    return report
