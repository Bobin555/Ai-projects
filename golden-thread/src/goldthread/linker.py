"""Link records by chunk-local keys or by alias-resolved codes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from goldthread.aliases import AliasTable, normalise_term
from goldthread.core import Link, Record, RecordSchema
from goldthread.store import Store


@dataclass
class LinkReport:
    created: int = 0  # links that did not exist before
    removed: int = 0  # links that no longer follow from the records (rejected or corrected)
    unresolved: list[str] = field(default_factory=list)  # "<record id>.<field>=<value>"


def link_records(store: Store, schema: RecordSchema, aliases: AliasTable) -> LinkReport:
    """Recompute all links from the records as they are now (links are derived state, never edited)."""
    by_type: dict[str, list[Record]] = defaultdict(list)
    for rec in store.records():
        if rec.status != "rejected":
            by_type[rec.type].append(rec)

    def canon(value: str) -> str:
        return normalise_term(aliases.canonical(value) or value)

    report = LinkReport()
    computed: list[Link] = []
    for lt in schema.link_types.values():
        for src in by_type.get(lt.from_type, []):
            value = str(src.fields.get(lt.field) or "").strip()
            if not value:
                continue
            targets = []
            for target_type, target_field in lt.targets.items():
                for target in by_type.get(target_type, []):
                    target_value = str(target.fields.get(target_field) or "").strip()
                    if not target_value or target.id == src.id:
                        continue
                    if lt.scope == "chunk":
                        match = target.chunk_id == src.chunk_id and target_value == value
                    else:
                        match = canon(target_value) == canon(value)
                    if match:
                        targets.append(target)
            if not targets:
                report.unresolved.append(f"{src.id}.{lt.field}={value}")
                continue
            for target in targets:
                computed.append(Link(target.id, lt.name, src.id) if lt.reverse else Link(src.id, lt.name, target.id))
    before, after = set(store.links()), set(computed)
    report.created, report.removed = len(after - before), len(before - after)
    store.replace_links(sorted(after, key=lambda l: (l.link_type, l.src, l.dst)))
    return report
