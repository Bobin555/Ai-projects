"""Render answers as Markdown or HTML."""
from __future__ import annotations

import html

from goldthread.answerer import Answer, Statement

REFUSAL_TEXT = 'The model declined to answer (refusal). This is not a "not found" result.'


def incomplete_text(answer: Answer) -> str:
    if not answer.statements:
        return (f"⚠ Incomplete answer: the model returned no text (stop reason: {answer.stop_reason or 'unknown'}). "
                'This is not a "not found" result; ask again.')
    return (f"⚠ Incomplete answer: the model stopped before finishing (stop reason: {answer.stop_reason}). "
            'The statements below may be cut short. This is not a "not found" result.')


def _statement_md(s: Statement) -> list[str]:
    if s.status == "verified":
        lines = [f"- {s.text}"]
    elif s.status == "flagged":
        reasons = "; ".join(sorted({c.reason for c in s.citations if not c.ok}))
        lines = [f"- ⚠ {s.text} (quote check failed: {reasons})"]
    elif s.status == "unsourced":
        return [f"- ⚠ no source: {s.text}"]
    else:
        return [f"- {s.text}"]
    for c in s.citations:
        mark = "" if c.ok else f" ⚠ {c.reason}"
        lines.append(f"  - `{c.address}` “{c.quote}”{mark}")
    return lines


def render_answer_md(answer: Answer, outside: str = "") -> str:
    head = f"**Question:** {answer.question}\n\n"
    if answer.kind == "refused":
        return head + REFUSAL_TEXT + "\n"
    if answer.kind == "not_found":
        body = ["Not found. Searched:", *[f"- {s}" for s in answer.searched]]
        if outside.strip():
            body += ["", "Outside this corpus:", outside.strip()]
        return head + "\n".join(body) + "\n"
    lines = [line for s in answer.statements for line in _statement_md(s)]
    if answer.kind == "incomplete":
        lines = [incomplete_text(answer), "", *lines]
    footer = f"\n\n_Model: {answer.model} · served by: {answer.served_by} · run: {answer.run_id}_"
    return head + "\n".join(lines) + footer + "\n"


def render_answer_html(answer: Answer, outside: str = "") -> str:
    e = html.escape
    parts = [f"<p><strong>Question:</strong> {e(answer.question)}</p>"]
    if answer.kind == "refused":
        parts.append(f"<p>{e(REFUSAL_TEXT)}</p>")
    elif answer.kind == "not_found":
        parts.append("<p>Not found. Searched:</p><ul>")
        parts += [f"<li>{e(s)}</li>" for s in answer.searched]
        parts.append("</ul>")
        if outside.strip():
            parts.append(f"<p>Outside this corpus:</p><pre>{e(outside.strip())}</pre>")
    else:
        if answer.kind == "incomplete":
            parts.append(f"<p><strong>{e(incomplete_text(answer))}</strong></p>")
        parts.append("<ul>")
        for s in answer.statements:
            prefix = {"flagged": "⚠ ", "unsourced": "⚠ no source: "}.get(s.status, "")
            cites = "".join(
                f"<li><code>{e(c.address)}</code> “{e(c.quote)}”{'' if c.ok else ' ⚠ ' + e(c.reason)}</li>"
                for c in s.citations)
            parts.append(f"<li>{e(prefix)}{e(s.text)}{'<ul>' + cites + '</ul>' if cites else ''}</li>")
        parts.append("</ul>")
        parts.append(f"<p><em>Model: {e(answer.model)} · served by: {e(answer.served_by)} · "
                     f"run: {e(answer.run_id)}</em></p>")
    return "<!doctype html><meta charset=\"utf-8\"><title>Answer</title>\n" + "\n".join(parts) + "\n"
