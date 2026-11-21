"""Record ids, the extraction JSON schema and field checks."""
from __future__ import annotations

import hashlib
from typing import Mapping, Sequence

from goldthread.aliases import normalise_term
from goldthread.core import RecordSchema, RecordType


def record_id(rt: RecordType, address: str, quote: str, fields: Mapping[str, str] | None = None) -> str:
    """Stable id from type, address, quote and the type's identity fields (so two claims quoting one sentence
    for different requirements stay two records)."""
    key = f"{rt.name}|{address}|{quote}"
    if rt.identity:
        key += "|" + "|".join(normalise_term(str((fields or {}).get(f) or "")) for f in rt.identity)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"{rt.prefix}-{digest[:8]}"


def _closed(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def extraction_schema(schema: RecordSchema, looks_for: Sequence[str], addresses: Sequence[str]) -> dict:
    field_names = list(dict.fromkeys(f for t in looks_for for f in schema.record_types[t].fields))
    field_item = _closed({"name": {"type": "string", "enum": field_names}, "value": {"type": "string"}})
    record = _closed({
        "type": {"type": "string", "enum": list(looks_for)},
        "key": {"type": "string"},
        "address": {"type": "string", "enum": list(addresses)},
        "quote": {"type": "string"},
        "fields": {"type": "array", "items": field_item},
    })
    return _closed({"records": {"type": "array", "items": record}})


def missing_required(rt: RecordType, fields: Mapping[str, str]) -> list[str]:
    return [name for name in rt.required if not str(fields.get(name) or "").strip()]
