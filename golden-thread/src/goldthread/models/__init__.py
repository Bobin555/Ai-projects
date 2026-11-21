"""Model connectors."""
from __future__ import annotations

import yaml

from goldthread.config import Pack, PackError
from goldthread.models.base import Connector
from goldthread.models.fake import FakeConnector


def get_connector(provider: str, pack: Pack | None = None, client: object | None = None) -> Connector:
    if provider == "fake":
        extractions = {}
        if pack is not None and (pack.root / "fake_extractions.yaml").is_file():
            extractions = yaml.safe_load((pack.root / "fake_extractions.yaml").read_text(encoding="utf-8")) or {}
        return FakeConnector(extractions=extractions)
    if provider == "claude":
        from goldthread.models.claude import ClaudeConnector
        return ClaudeConnector(client)
    raise PackError(f"unknown provider '{provider}'")
