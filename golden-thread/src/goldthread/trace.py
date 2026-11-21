"""Trace a requirement (or any record) through its links."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from goldthread.aliases import AliasTable, normalise_term
from goldthread.core import Record
from goldthread.store import Store
from goldthread.verifier import Verification, verify_quote


@dataclass
class TraceNode:
    record: Record
    via: str  # "" for a root, otherwise "<- meets", "-> cites", ...
    check: Verification  # the quote re-checked against the store now, not when it was reviewed
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
    def node_of(rec: Record, via: str) -> TraceNode:
        return TraceNode(rec, via, verify_quote(store, rec.address, rec.quote))

    nodes = [node_of(r, "") for r in roots]
    visited = {r.id for r in roots}
    frontier = list(nodes)
    for _ in range(max_depth):
        next_frontier: list[TraceNode] = []
        for node in frontier:
            # A node reached by following a link outwards (e.g. the method an argument follows) is shared:
            # going back in through the same link type would pull in its other users, which are not this thread.
            came_out_by = node.via[3:] if node.via.startswith("-> ") else None
            neighbours = [(f"<- {l.link_type}", l.src) for l in store.links(dst=node.record.id)
                          if l.link_type != came_out_by]
            neighbours += [(f"-> {l.link_type}", l.dst) for l in store.links(src=node.record.id)]
            for via, record_id in sorted(neighbours):
                if record_id in visited:
                    continue
                rec = store.record(record_id)
                if rec is None or rec.status == "rejected":
                    continue
                visited.add(record_id)
                child = node_of(rec, via)
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
    if not node.check.ok and f"quote_failed: {node.check.reason}" not in r.flags:
        parts.append(f" · ⚠ quote check failed: {node.check.reason}")
    return "  " * depth + "- " + "".join(parts)


def render_trace_md(nodes: list[TraceNode], searched: Sequence[str], not_extracted: Sequence[str] = ()) -> str:
    """Markdown trace. `searched` lists the documents whose records were searched; `not_extracted` the issued
    documents with no records yet, so a short or empty trace is never read as complete."""
    tail = ("\nNot yet extracted:\n" + "\n".join(f"- {s}" for s in not_extracted) + "\n") if not_extracted else ""
    if not nodes:
        return "Not found. Searched:\n" + "\n".join(f"- {s}" for s in searched) + "\n" + tail
    lines: list[str] = []

    def walk(node: TraceNode, depth: int) -> None:
        lines.append(_line(node, depth))
        for child in node.children:
            walk(child, depth + 1)

    for node in nodes:
        walk(node, 0)
    return "\n".join(lines) + "\n" + tail
