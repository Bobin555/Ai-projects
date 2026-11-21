"""Trace a requirement (or any record) through its links."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from goldthread.aliases import AliasTable, normalise_term
from goldthread.core import Record
from goldthread.store import Store


@dataclass
class TraceNode:
    record: Record
    via: str  # "" for a root, otherwise "<- meets", "-> cites", ...
    children: list["TraceNode"] = field(default_factory=list)


def _canon(aliases: AliasTable, value: str) -> str:
    return normalise_term(aliases.canonical(value) or value)


def trace(store: Store, aliases: AliasTable, start: str, max_depth: int = 4) -> list[TraceNode]:
    root = store.record(start)
    if root is not None and root.status != "rejected":
        roots = [root]
    else:
        wanted = _canon(aliases, start)
        roots = [r for r in store.records() if r.status != "rejected" and str(r.fields.get("code") or "").strip()
                 and _canon(aliases, str(r.fields["code"])) == wanted]
    nodes = [TraceNode(r, "") for r in roots]
    visited = {r.id for r in roots}
    frontier = list(nodes)
    for _ in range(max_depth):
        next_frontier: list[TraceNode] = []
        for node in frontier:
            neighbours = [(f"<- {l.link_type}", l.src) for l in store.links(dst=node.record.id)]
            neighbours += [(f"-> {l.link_type}", l.dst) for l in store.links(src=node.record.id)]
            for via, record_id in sorted(neighbours):
                if record_id in visited:
                    continue
                rec = store.record(record_id)
                if rec is None or rec.status == "rejected":
                    continue
                visited.add(record_id)
                child = TraceNode(rec, via)
                node.children.append(child)
                next_frontier.append(child)
        frontier = next_frontier
    return nodes


def _line(node: TraceNode, depth: int) -> str:
    r = node.record
    parts = [f"{node.via} · " if node.via else "", f"**{r.type}** {r.id} [{r.status}]"]
    if r.status == "draft":
        parts.append(" (draft, not yet reviewed)")
    parts.append(f" · `{r.address}` “{r.quote}”")
    shown = [f"{k}: {v}" for k, v in r.fields.items() if k != "key" and str(v).strip()]
    if shown:
        parts.append(" · " + "; ".join(shown))
    if r.type == "EvidenceRef":
        parts.append(" — cited, not available in this pack")
    if r.flags:
        parts.append(" · " + "; ".join(f"⚠ {f}" for f in r.flags))
    return "  " * depth + "- " + "".join(parts)


def render_trace_md(nodes: list[TraceNode], searched: Sequence[str]) -> str:
    if not nodes:
        return "Not found. Searched:\n" + "\n".join(f"- {s}" for s in searched) + "\n"
    lines: list[str] = []

    def walk(node: TraceNode, depth: int) -> None:
        lines.append(_line(node, depth))
        for child in node.children:
            walk(child, depth + 1)

    for node in nodes:
        walk(node, 0)
    return "\n".join(lines) + "\n"
