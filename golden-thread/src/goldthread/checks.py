"""Coverage rules from the pack schema, and citations of superseded revisions."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from goldthread.core import RecordSchema
from goldthread.store import Store


@dataclass
class CheckReport:
    coverage: dict[str, list[str]] = field(default_factory=dict)  # rule name -> record ids
    superseded_citations: list[str] = field(default_factory=list)


def run_checks(store: Store, schema: RecordSchema) -> CheckReport:
    records = [r for r in store.records() if r.status != "rejected"]
    live = {r.id for r in records}
    incoming: dict[tuple[str, str], set[str]] = defaultdict(set)
    outgoing: dict[tuple[str, str], set[str]] = defaultdict(set)
    for link in store.links():
        if link.src not in live or link.dst not in live:
            continue
        incoming[(link.dst, link.link_type)].add(link.src)
        outgoing[(link.src, link.link_type)].add(link.dst)

    report = CheckReport()
    for rule in schema.coverage:
        ids = []
        for r in records:
            if r.type != rule.type:
                continue
            if rule.missing_incoming and not incoming.get((r.id, rule.missing_incoming)):
                ids.append(r.id)
            elif rule.has_incoming and incoming.get((r.id, rule.has_incoming)):
                ids.append(r.id)
            elif rule.has_outgoing and outgoing.get((r.id, rule.has_outgoing)):
                ids.append(r.id)
        report.coverage[rule.name] = ids

    for r in records:
        doc_id, _, revision = r.address.split("#")[0].partition("@")
        document = store.document(doc_id, revision)
        if document is not None and document.status == "superseded":
            report.superseded_citations.append(r.id)
    return report


def render_checks_md(report: CheckReport) -> str:
    lines = ["## Coverage"]
    for name, ids in report.coverage.items():
        lines.append(f"### {name} ({len(ids)})")
        lines += [f"- {i}" for i in ids] or ["- none"]
    lines.append(f"## Citations of superseded revisions ({len(report.superseded_citations)})")
    lines += [f"- {i}" for i in report.superseded_citations] or ["- none"]
    return "\n".join(lines) + "\n"
