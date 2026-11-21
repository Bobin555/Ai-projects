"""SQLite store: documents, passages (with FTS5), records, links and extraction progress."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Mapping, Sequence

from goldthread.core import DocumentEntry, Link, Passage, Record

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT, revision TEXT, title TEXT, layout TEXT, date TEXT,
    status TEXT, supersedes TEXT, url TEXT, sha256 TEXT,
    PRIMARY KEY (doc_id, revision)
);
CREATE TABLE IF NOT EXISTS passages (
    address TEXT UNIQUE, doc_id TEXT, revision TEXT, page INTEGER, n INTEGER,
    heading TEXT, text TEXT, kind TEXT
);
CREATE INDEX IF NOT EXISTS passages_doc ON passages (doc_id, revision, page, n);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5 (address UNINDEXED, heading, text);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY, type TEXT, fields_json TEXT, address TEXT, quote TEXT, status TEXT,
    flags_json TEXT, extracted_by TEXT, run_id TEXT, chunk_id TEXT, reviewed_by TEXT, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS links (src TEXT, link_type TEXT, dst TEXT, PRIMARY KEY (src, link_type, dst));
CREATE TABLE IF NOT EXISTS extract_progress (run_id TEXT, chunk_id TEXT, PRIMARY KEY (run_id, chunk_id));
"""

_PASSAGE_COLS = "p.address, p.doc_id, p.revision, p.page, p.n, p.heading, p.text, p.kind"
_DOC_COLS = "doc_id, title, layout, revision, date, status, supersedes, url, sha256"


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- documents ------------------------------------------------------------

    def upsert_document(self, entry: DocumentEntry) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO documents ({_DOC_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.doc_id, entry.title, entry.layout, entry.revision, entry.date,
             entry.status, entry.supersedes, entry.url, entry.sha256),
        )
        self.db.commit()

    def document(self, doc_id: str, revision: str) -> DocumentEntry | None:
        row = self.db.execute(f"SELECT {_DOC_COLS} FROM documents WHERE doc_id = ? AND revision = ?",
                              (doc_id, revision)).fetchone()
        return DocumentEntry(*row) if row else None

    def documents(self, status: str | None = None) -> list[DocumentEntry]:
        sql = f"SELECT {_DOC_COLS} FROM documents"
        args: tuple = ()
        if status is not None:
            sql += " WHERE status = ?"
            args = (status,)
        rows = self.db.execute(sql + " ORDER BY doc_id, revision", args).fetchall()
        return [DocumentEntry(*r) for r in rows]

    # --- passages -------------------------------------------------------------

    def replace_passages(self, doc_id: str, revision: str, passages: Sequence[Passage]) -> None:
        with self.db:
            self.db.execute(
                "DELETE FROM passages_fts WHERE rowid IN "
                "(SELECT rowid FROM passages WHERE doc_id = ? AND revision = ?)", (doc_id, revision))
            self.db.execute("DELETE FROM passages WHERE doc_id = ? AND revision = ?", (doc_id, revision))
            for p in passages:
                cur = self.db.execute(
                    "INSERT INTO passages (address, doc_id, revision, page, n, heading, text, kind) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (p.address, p.doc_id, p.revision, p.page, p.n, p.heading, p.text, p.kind))
                self.db.execute("INSERT INTO passages_fts (rowid, address, heading, text) VALUES (?, ?, ?, ?)",
                                (cur.lastrowid, p.address, p.heading, p.text))

    def passage(self, address: str) -> Passage | None:
        row = self.db.execute(f"SELECT {_PASSAGE_COLS} FROM passages p WHERE p.address = ?",
                              (address,)).fetchone()
        return Passage(*row) if row else None

    def passages_of(self, doc_id: str, revision: str) -> list[Passage]:
        rows = self.db.execute(
            f"SELECT {_PASSAGE_COLS} FROM passages p WHERE p.doc_id = ? AND p.revision = ? ORDER BY p.page, p.n",
            (doc_id, revision)).fetchall()
        return [Passage(*r) for r in rows]

    def fts_search(self, match_expr: str, include_superseded: bool, limit: int) -> list[tuple[Passage, float]]:
        rows = self.db.execute(
            f"SELECT {_PASSAGE_COLS}, bm25(passages_fts) AS score "
            "FROM passages_fts JOIN passages p ON p.rowid = passages_fts.rowid "
            "JOIN documents d ON d.doc_id = p.doc_id AND d.revision = p.revision "
            "WHERE passages_fts MATCH ? AND (? OR d.status = 'issued') "
            "ORDER BY score LIMIT ?",
            (match_expr, 1 if include_superseded else 0, limit)).fetchall()
        return [(Passage(*r[:8]), r[8]) for r in rows]

    # --- records --------------------------------------------------------------

    def upsert_record(self, rec: Record) -> None:
        existing = self.record(rec.id)
        if existing is not None and existing.status in REVIEWED:
            return
        self.db.execute(
            f"INSERT INTO records ({_RECORD_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET type = excluded.type, fields_json = excluded.fields_json, "
            "address = excluded.address, quote = excluded.quote, status = excluded.status, "
            "flags_json = excluded.flags_json, extracted_by = excluded.extracted_by, run_id = excluded.run_id, "
            "chunk_id = excluded.chunk_id, reviewed_by = excluded.reviewed_by, reviewed_at = excluded.reviewed_at",
            (rec.id, rec.type, json.dumps(dict(rec.fields)), rec.address, rec.quote, rec.status,
             json.dumps(list(rec.flags)), rec.extracted_by, rec.run_id, rec.chunk_id, rec.reviewed_by,
             rec.reviewed_at))
        self.db.commit()

    def record(self, id: str) -> Record | None:
        row = self.db.execute(f"SELECT {_RECORD_COLS} FROM records WHERE id = ?", (id,)).fetchone()
        return _record(row) if row else None

    def records(self, type: str | None = None) -> list[Record]:
        sql, args = f"SELECT {_RECORD_COLS} FROM records", ()
        if type is not None:
            sql, args = sql + " WHERE type = ?", (type,)
        return [_record(r) for r in self.db.execute(sql + " ORDER BY rowid", args).fetchall()]

    def set_review(self, id: str, status: str, reviewer: str, at: str, fields: Mapping[str, str] | None,
                   quote: str | None, flags: tuple[str, ...]) -> None:
        self.db.execute(
            "UPDATE records SET status = ?, reviewed_by = ?, reviewed_at = ?, flags_json = ?, "
            "fields_json = COALESCE(?, fields_json), quote = COALESCE(?, quote) WHERE id = ?",
            (status, reviewer, at, json.dumps(list(flags)),
             json.dumps(dict(fields)) if fields is not None else None, quote, id))
        self.db.commit()

    # --- links ----------------------------------------------------------------

    def add_link(self, link: Link) -> None:
        self.db.execute("INSERT OR IGNORE INTO links (src, link_type, dst) VALUES (?, ?, ?)",
                        (link.src, link.link_type, link.dst))
        self.db.commit()

    def replace_links(self, links: Sequence[Link]) -> None:
        """Links are derived from records: replace them all at once."""
        with self.db:
            self.db.execute("DELETE FROM links")
            self.db.executemany("INSERT OR IGNORE INTO links (src, link_type, dst) VALUES (?, ?, ?)",
                                [(l.src, l.link_type, l.dst) for l in links])

    def links(self, src: str | None = None, dst: str | None = None, link_type: str | None = None) -> list[Link]:
        clauses, args = [], []
        for column, value in (("src", src), ("dst", dst), ("link_type", link_type)):
            if value is not None:
                clauses.append(f"{column} = ?")
                args.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.execute(f"SELECT src, link_type, dst FROM links{where} ORDER BY link_type, src, dst",
                               args).fetchall()
        return [Link(*r) for r in rows]

    # --- extraction progress ----------------------------------------------------

    def mark_chunk_done(self, run_id: str, chunk_id: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO extract_progress (run_id, chunk_id) VALUES (?, ?)", (run_id, chunk_id))
        self.db.commit()

    def chunks_done(self, run_id: str) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT chunk_id FROM extract_progress WHERE run_id = ?", (run_id,))}

    def chunks_done_any_run(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT chunk_id FROM extract_progress")}


REVIEWED = ("verified", "corrected", "rejected")
_RECORD_COLS = ("id, type, fields_json, address, quote, status, flags_json, extracted_by, run_id, chunk_id, "
                "reviewed_by, reviewed_at")


def _record(row: tuple) -> Record:
    (id_, type_, fields_json, address, quote, status, flags_json, extracted_by, run_id, chunk_id,
     reviewed_by, reviewed_at) = row
    return Record(id_, type_, json.loads(fields_json), address, quote, status, tuple(json.loads(flags_json)),
                  extracted_by, run_id, chunk_id, reviewed_by, reviewed_at)
