# Golden Thread Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Golden Thread engine (fetch, read, store, search, answer with verified quotes, extract and link records, review, trace, checks, evaluation, budget guard, CLI) and the public `nrc-xenergy` pack, using the Claude connector only.

**Architecture:** A Python package `goldthread` under `golden-thread/src/`. Every pack is a folder of configuration files; all pack data (downloads, SQLite stores, logs, ledger, reports, review sheets) lives under a git-ignored data directory. Models sit behind one `Connector` interface: `ClaudeConnector` for real runs and a deterministic `FakeConnector` for tests. A model-independent quote verifier checks every citation.

**Tech Stack:** Python ≥3.11 (container has 3.13), SQLite FTS5 (stdlib `sqlite3`), pdfplumber, PyYAML, anthropic SDK (2.x); dev: pytest, reportlab (test PDF generation).

**Spec:** `docs/superpowers/specs/2026-11-20-golden-thread-design.md`

## Global Constraints

- Runtime dependencies: `pdfplumber>=0.11`, `PyYAML>=6`, `anthropic>=2.12` only. Dev: `pytest>=9`, `reportlab>=5`.
- Passage address format: `doc_id@rev#p<page>.<n>` (`doc_id` and `revision` match `^[A-Za-z0-9._-]+$`).
- 100% of quotes displayed as verified pass the verifier (hard rule).
- "Not found" always lists the documents and revisions searched.
- Newest issued revision wins: search excludes `superseded` documents by default; citing a superseded revision fails verification.
- `[withheld]` text is reported as withheld, never inferred.
- Records start `draft`; reviews set `verified`, `corrected` or `rejected`, with reviewer and time.
- Default models: `claude-opus-5-5` for every job; effort `low` for `extract` and `judge`, `high` for `answer`.
- Default budget for the public pack: `per_run_usd: 20`, `per_month_usd: 150`.
- A pack with `offline: true` never makes a network call: hosted providers refused at load, `fetch` refused, commands run inside `no_network()`. A `sensitive` pack must be `offline`.
- Claude calls use `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`; the serving model (`response.model`) is recorded. Never send `temperature`, `top_p` or `top_k`.
- Citations (`search_result` blocks with `citations: {"enabled": true}`) and `output_config.format` are never in the same request.
- Never committed: anything under `golden-thread/data/` (documents, stores, logs, ledger, reports, review sheets), `.venv/`.
- HTTP requests carry `User-Agent: golden-thread/0.1` and no personal details.
- Success thresholds: retrieval (expected source in top 10) ≥ 0.80; every out-of-corpus question answered "not found".
- Every commit message ends with the session's attribution lines.

**Not in this plan** (later, per the spec): embedding search, the Batch API, the OpenAI-compatible connector (phase 2), OCR, value-consistency checks, a web interface, per-document access control.

## Review Focus

1. **Identifier near-misses:** a question about `50.34(a)` must not retrieve a passage that only says `50.34(b)`; `PDC 1` must not match `PDC 10`. Test in Task 5.
2. **Review sheet edited in Excel:** UTF-8 BOM, reordered columns and a hand-edited quote must import correctly; the edited quote is re-verified, and the record is flagged if it fails. Test in Task 12.
3. **A document that changed on the server:** a re-download whose checksum differs is quarantined and never ingested; ingest refuses a file whose checksum doesn't match the register. Tests in Tasks 3 and 4.
4. **Scanned pages and withheld text:** a page with no text layer becomes a flagged `no_text` passage, and withheld markers make a `withheld` passage. Both are counted in the ingest report, never silently dropped. Tests in Tasks 2 and 3.
5. **Refusals and fallbacks:** a refusal is reported as "refused", never as "not found". An answer served by a fallback model records that model, and an unknown serving model is priced at the most expensive table price and flagged. Tests in Tasks 7, 9 and 10.

## Execution Prerequisites

- Work from `golden-thread/`: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`. Tests: `.venv/bin/pytest -q`.
- Task 16 needs nrc.gov reachable from the session (blocked as of 2026-11-20: request access with the environment tool) or the user uploading the PDFs.
- Task 17 spends API credit: it starts only after the user says yes.

## File Structure

```
golden-thread/
  pyproject.toml, .gitignore, README.md
  src/goldthread/
    __init__.py, __main__.py
    core.py        dataclasses shared by all modules
    config.py      load and validate packs; pack_version; register checksum update
    reader.py      PDF → passages (pdfplumber)
    store.py       SQLite: documents, passages (FTS5), records, links, extraction progress
    ingest.py      register + files → store, with checksum checks
    fetch.py       download into cache, record/verify checksums
    netguard.py    no_network() context manager
    aliases.py     alias table
    search.py      keyword search with aliases and exact identifiers
    verifier.py    quote normalisation and verification
    prices.yaml    dated price table
    budget.py      prices, ledger, budget guard, cost summary
    models/__init__.py  get_connector()
    models/base.py      Prompt, Raw* results, Connector protocol
    models/fake.py      deterministic connector for tests
    models/claude.py    Claude connector
    answerer.py    ask(): search → model → verified statements
    audit.py       JSON-lines audit log
    render.py      Markdown/HTML answers
    records.py     record ids, extraction JSON schema, field validation
    extractor.py   chunking and extraction runs with resume
    linker.py      link records by chunk keys and alias-resolved codes
    review.py      review sheet export/import
    trace.py       trace from a code or record
    checks.py      coverage rules and revision drift
    evaluate.py    run tests.csv, metrics, report
    cli.py         command line
  packs/nrc-xenergy/   pack.yaml, register.csv, records.yaml, layouts/*.yaml, aliases.csv,
                       rules.md, answer_format.md, outside.md, tests.csv
  tests/
    conftest.py
    fixtures/pdfs.py, fixtures/synthetic_docs.py
    fixtures/packs/synthetic/   (same file set as a pack + fake_extractions.yaml)
    test_*.py
```

---

### Task 1: Project scaffold, core types and pack loading

**Files:**
- Create: `golden-thread/pyproject.toml`, `golden-thread/.gitignore`, `src/goldthread/__init__.py`, `src/goldthread/core.py`, `src/goldthread/config.py`
- Create: `tests/fixtures/packs/synthetic/` with `pack.yaml`, `register.csv`, `records.yaml`, `layouts/regulatory_guide.yaml`, `layouts/safety_report.yaml`, `layouts/safety_evaluation.yaml`, `aliases.csv`, `rules.md`, `answer_format.md`, `outside.md`, `tests.csv` (and `fake_extractions.yaml` in Task 11)
- Test: `tests/test_config.py`, `tests/conftest.py` (fixture `synthetic_pack_dir`: copies the fixture pack into `tmp_path/"packs/synthetic"` and returns the path)

**Interfaces:**
- Produces (`core.py`, all `@dataclass(frozen=True)`):
  - `JOBS = ("extract", "answer", "judge")`
  - `ModelSpec(provider: str, model: str, effort: str = "medium", max_tokens: int = 16000)`
  - `Budget(per_run_usd: float, per_month_usd: float)`
  - `DocumentEntry(doc_id, title, layout, revision, date, status, supersedes, url, sha256)`, all `str`; `status` is `"issued"` or `"superseded"`; `supersedes` is `"doc_id@rev"` or `""`
  - `Passage(address: str, doc_id: str, revision: str, page: int, n: int, heading: str, text: str, kind: str)`, where `kind` is `"text"`, `"table"`, `"withheld"` or `"no_text"`
  - `Usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)`
  - `EvalCase(id: str, question: str, expected_sources: tuple[str, ...], expected_point: str, expect_not_found: bool, status: str)`, where `status` is `"draft"` or `"approved"`
  - `RecordType(name: str, prefix: str, fields: tuple[str, ...], required: tuple[str, ...])`
  - `LinkType(name: str, from_type: str, field: str, targets: Mapping[str, str], scope: str, reverse: bool)`. `targets` maps a record type to the field matched there; `scope` is `"chunk"` or `"code"`; `reverse` stores the link as target → source.
  - `CoverageRule(name: str, type: str, missing_incoming: str = "", has_incoming: str = "", has_outgoing: str = "")`
  - `RecordSchema(record_types: Mapping[str, RecordType], link_types: Mapping[str, LinkType], coverage: tuple[CoverageRule, ...])`
  - `LayoutRecipe(layout: str, looks_for: tuple[str, ...], instructions: str, example: str)`
  - `Record(id, type, fields: Mapping[str, str], address, quote, status, flags: tuple[str, ...], extracted_by, run_id, chunk_id, reviewed_by, reviewed_at)`
  - `Link(src: str, link_type: str, dst: str)`
- Produces (`config.py`):
  - `class PackError(Exception)`
  - `HOSTED_PROVIDERS = {"claude"}`, `LOCAL_PROVIDERS = {"fake"}`, `ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")`
  - `Pack` (frozen dataclass): `name, description, sensitivity, offline: bool, source_dir: Path | None, withheld_patterns: tuple[str, ...], models: Mapping[str, ModelSpec], budget: Budget, register: tuple[DocumentEntry, ...], schema: RecordSchema, layouts: Mapping[str, LayoutRecipe], aliases_path: Path, rules: str, answer_format: str, outside: str, tests: tuple[EvalCase, ...], root: Path, data_dir: Path`
  - `load_pack(root: Path, data_root: Path | None = None) -> Pack`. `data_root` defaults to `$GT_DATA_DIR`, otherwise `Path.cwd() / "data"`; `data_dir = data_root / name`; `source_dir` is resolved relative to `root`.
  - `pack_version(pack: Pack) -> str`: the first 12 hex characters of a sha256 over the sorted relative paths and bytes of every file under `pack.root`
  - `update_register_checksum(pack: Pack, doc_id: str, revision: str, sha256: str) -> None`: rewrites that row's `sha256` cell in `register.csv`, keeping the other rows byte-identical

File formats (pinned):
- `pack.yaml` keys: `name, description, sensitivity (public|sensitive), offline, source_dir, withheld_patterns, models{extract,answer,judge: {provider, model, effort, max_tokens}}, budget{per_run_usd, per_month_usd}`
- `register.csv` header: `doc_id,title,layout,revision,date,status,supersedes,url,sha256`
- `tests.csv` header: `id,question,expected_sources,expected_point,expect_not_found,status` (sources separated by `;`; `expect_not_found` is `yes`/`no`)
- `aliases.csv` header: `canonical,alias`
- `records.yaml`: `record_types: {Name: {prefix, fields: [...], required: [...]}}`, `link_types: {name: {from, field, to: {Type: field}, scope, reverse}}`, `coverage: [{name, type, missing_incoming|has_incoming|has_outgoing}]`
- `layouts/<layout>.yaml`: `layout, looks_for: [...], instructions, example`

Synthetic pack: `offline: true`, `source_dir: source`, `withheld_patterns: ['\[\[.*?\]\]']`, all three jobs `{provider: fake, model: fake, effort: high|low, max_tokens: 4000}`, budget `{per_run_usd: 1.0, per_month_usd: 5.0}`.
- Register rows: `SYN-RG1@r1` (regulatory_guide, issued), `SYN-SAR@r1` (safety_report, superseded), `SYN-SAR@r2` (safety_report, issued, supersedes `SYN-SAR@r1`), `SYN-SE@r1` (safety_evaluation, issued). Empty `url` and `sha256`.
- `records.yaml`: the same seven record types, link types and coverage rules as the nrc-xenergy pack (Task 16 table).
- Aliases: `PDC 10` ← `Criterion 10`, `MHTGR-DC 10`; `10 CFR 50.34(a)` ← `50.34(a)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_load_synthetic_pack(synthetic_pack_dir, tmp_path):
    pack = load_pack(synthetic_pack_dir, data_root=tmp_path / "data")
    assert pack.name == "synthetic" and pack.offline is True
    assert pack.models["answer"] == ModelSpec("fake", "fake", "high", 4000)
    assert pack.budget == Budget(1.0, 5.0)
    assert [f"{e.doc_id}@{e.revision}" for e in pack.register] == [
        "SYN-RG1@r1", "SYN-SAR@r1", "SYN-SAR@r2", "SYN-SE@r1"]
    assert pack.register[2].supersedes == "SYN-SAR@r1"
    assert pack.data_dir == tmp_path / "data" / "synthetic"
    assert pack.schema.link_types["meets"].targets == {"Requirement": "code"}
```

Tests to write (one function each, asserting `PackError` and the message substring):
- `test_offline_pack_rejects_hosted_provider`: answer provider set to `claude` raises "offline pack cannot use hosted provider 'claude' for job 'answer'"
- `test_sensitive_pack_must_be_offline`: `sensitivity: sensitive`, `offline: false` raises "sensitive pack must be offline"
- `test_missing_file_named`: deleting `rules.md` raises a message containing "rules.md"
- `test_unknown_provider`: `provider: magic` raises "unknown provider 'magic'"
- `test_bad_doc_id`: `doc_id` `"ML 123"` raises "invalid doc_id 'ML 123'"
- `test_duplicate_register_row` raises "duplicate register row SYN-RG1@r1"
- `test_supersedes_must_exist` raises "supersedes unknown SYN-XX@r9"
- `test_link_type_unknown_record_type` raises "unknown record type"
- `test_pack_version_stable_and_changes`: same value twice, and a different value after appending to `rules.md`
- `test_update_register_checksum`: after the update, only that row's `sha256` differs

- [ ] **Step 2: Run to verify they fail**
Run: `.venv/bin/pytest tests/test_config.py -q`. Expected: FAIL (ImportError: goldthread.config).

- [ ] **Step 3: Implement `core.py` and `config.py`** with the signatures above. `pyproject.toml`: project `golden-thread` 0.1.0, `requires-python = ">=3.11"`, src layout, dependencies and the `dev` extra as in Global Constraints, script `goldthread = "goldthread.cli:main"`. `.gitignore`: `data/`, `.venv/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`.

- [ ] **Step 4: Run tests to verify they pass.** `.venv/bin/pytest tests/test_config.py -q` → all pass.

- [ ] **Step 5: Commit** `golden-thread/` (`feat: scaffold goldthread with pack loading and validation`).

---

### Task 2: Test PDFs and the PDF reader

**Files:**
- Create: `tests/fixtures/pdfs.py`, `tests/fixtures/synthetic_docs.py`, `src/goldthread/reader.py`
- Modify: `tests/conftest.py` (fixture `synthetic_pack`, below)
- Test: `tests/test_reader.py`

**Interfaces:**
- Consumes: `DocumentEntry`, `Passage` (Task 1)
- Produces:
  - `address_of(doc_id: str, revision: str, page: int, n: int) -> str`
  - `read_pdf(path: Path, entry: DocumentEntry, withheld_patterns: Sequence[str] = ()) -> list[Passage]`
  - Test helpers:
    - `make_pdf(path: Path, pages: list[list[Block]]) -> None`, where `Block` is `Heading(text)`, `Para(text)` (wrapped at 90 characters per line), `Table(rows: list[list[str]])` or `ImageOnly()`. Blocks are separated by a vertical gap of one line height. Uses reportlab `canvas.Canvas(..., invariant=1)` and a 1-cell-per-column `Table` drawn with grid lines.
    - `DOCS: dict[str, list[list[Block]]]` keyed `"SYN-RG1@r1"` and so on.
    - `pdf_path(pack: Pack, key: str) -> Path` and `entry_of(pack: Pack, key: str) -> DocumentEntry`, where `key` is `"doc_id@rev"`.
  - Fixture `synthetic_pack(synthetic_pack_dir, tmp_path) -> Pack`: builds every `DOCS` PDF into `<pack>/source/<doc_id>@<rev>.pdf`, writes their sha256 into the copied `register.csv`, and returns `load_pack(..., data_root=tmp_path/"data")`.
  - Fixture `rg1(synthetic_pack) -> list[Passage]`: `read_pdf(pdf_path(pack, "SYN-RG1@r1"), entry_of(pack, "SYN-RG1@r1"))`.

Synthetic document text (later tasks quote these sentences exactly):
- `SYN-RG1@r1`:
  - p1: `Heading("1 Scope")`, `Para("This guide applies to modular reactors.")`, `Heading("2 Criteria")`, `Heading("2.1 Criterion 10")`, `Para("The reactor core shall be designed so that fuel design limits are not exceeded during normal operation and anticipated operational occurrences, with appropriate margin for uncertainties.")`
  - p2: `Table([["Criterion","Topic"],["10","Reactor design"],["16","Containment"]])`, `Heading("2.2 Criterion 11")`, `Para("The reactor shall have inherent protection against reactivity increases.")`
  - p3: `ImageOnly()`
- `SYN-SAR@r1`: p1 `Heading("3.2 Fuel")`, `Para("The fuel temperature limit is 1600 C.")`
- `SYN-SAR@r2`:
  - p1: `Heading("3.2 Fuel")`, `Para("The fuel temperature limit is 1650 C.")`, `Para("The design meets Criterion 10 because the core keeps fuel below the limit.")`, `Para("Fuel performance is confirmed in report TR-123.")`, `Para("Burnup data are [[ proprietary ]] and withheld.")`
  - p2: `Heading("4 Licensing")`, `Para("10 CFR 50.34(a) requires a preliminary safety analysis report.")`, `Para("Section 50.34(b) is outside the scope of this report.")`
- `SYN-SE@r1`: p1 `Heading("4 Evaluation")`, `Para("The staff finds the fuel design acceptable for PDC 10, subject to Condition 1.")`, `Para("Condition 1: The applicant shall confirm the temperature limit before operation.")`

Reader rules (decisions the tests don't fully pin):
- Per page, find tables with `page.find_tables()`. Each table becomes one `kind="table"` passage, with rows joined as `" | ".join(cells)` and lines joined with `"\n"`. Remove table regions from the page with `page.outside_bbox(bbox)` before reading lines.
- Read lines with `extract_text_lines()`. Start a new passage when the vertical gap to the previous line is greater than 0.6 × the median line height, or when the line is a heading.
- A heading is a line matching `^(\d+(?:\.\d+)*)\.?\s+\S` with at most 100 characters and no final period. Its depth is the number of numeric parts. The heading path is joined with `" > "`, and a deeper heading pops shallower siblings.
- A passage's `text` is its lines joined with `"\n"`, exactly as extracted. A passage matching any of `withheld_patterns` gets `kind="withheld"`.
- A page with no characters becomes a single passage `kind="no_text"`, `text=""`, `n=1`.
- `n` counts passages per page from 1.

- [ ] **Step 1: Write the failing tests**

```python
def test_passages_have_address_heading_and_exact_text(rg1):
    p = next(p for p in rg1 if "fuel design limits" in p.text)
    assert re.fullmatch(r"SYN-RG1@r1#p1\.\d+", p.address)
    assert p.heading == "2 Criteria > 2.1 Criterion 10"
    assert " ".join(p.text.split()).startswith("The reactor core shall be designed")
    assert "\n" in p.text            # wrapped lines kept exactly as extracted

def test_heading_path_pops_siblings(rg1):
    p = next(p for p in rg1 if "inherent protection" in p.text)
    assert p.heading == "2 Criteria > 2.2 Criterion 11"

def test_table_passage(rg1):
    t = next(p for p in rg1 if p.kind == "table")
    assert "10 | Reactor design" in t.text and t.page == 2

def test_image_only_page_flagged_no_text(rg1):                     # Review Focus 4
    assert [p for p in rg1 if p.page == 3] == [
        Passage("SYN-RG1@r1#p3.1", "SYN-RG1", "r1", 3, 1, "", "", "no_text")]

def test_withheld_marker_passage(synthetic_pack):                   # Review Focus 4
    ps = read_pdf(pdf_path(synthetic_pack, "SYN-SAR@r2"),
                  entry_of(synthetic_pack, "SYN-SAR@r2"), [r"\[\[.*?\]\]"])
    w = next(p for p in ps if "[[ proprietary ]]" in p.text)
    assert w.kind == "withheld"
```

- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_reader.py -q` → FAIL (ImportError).
- [ ] **Step 3: Implement `make_pdf`, `DOCS`, the `synthetic_pack` fixture and `reader.py`** per the rules above.
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest tests/test_reader.py -q` → pass.
- [ ] **Step 5: Commit** (`feat: PDF reader with headings, tables, withheld and no-text passages`).

---

### Task 3: Store and ingest

**Files:**
- Create: `src/goldthread/store.py`, `src/goldthread/ingest.py`
- Test: `tests/test_store_ingest.py` (fixture `store`: `Store(tmp_path/"store.sqlite3")` after `ingest_pack(synthetic_pack, ...)`)

**Interfaces:**
- Consumes: `Pack`, `read_pdf`, core types
- Produces:
  - `Store(path: Path)` creates its schema on open. Tables:
    - `documents` (key `doc_id, revision`)
    - `passages` (key `address`)
    - `passages_fts`: FTS5 with columns `address UNINDEXED, heading, text`
    - `records`, `links`, and `extract_progress(run_id, chunk_id)`, used from Task 11
  - Methods:
    - `upsert_document(entry: DocumentEntry) -> None`
    - `replace_passages(doc_id: str, revision: str, passages: Sequence[Passage]) -> None`
    - `passage(address: str) -> Passage | None`
    - `document(doc_id: str, revision: str) -> DocumentEntry | None`
    - `documents(status: str | None = None) -> list[DocumentEntry]`
    - `fts_search(match_expr: str, include_superseded: bool, limit: int) -> list[tuple[Passage, float]]`: bm25 ascending, joined to `documents`, filtered to `status='issued'` unless `include_superseded`
    - `passages_of(doc_id: str, revision: str) -> list[Passage]`, in page then n order
  - `source_path(pack: Pack, entry: DocumentEntry) -> Path`: `pack.source_dir/<doc_id>@<rev>.pdf` when `offline`, otherwise `pack.data_dir/"cache"/<doc_id>@<rev>.pdf`
  - `IngestReport(documents: int, passages: int, flagged: list[str], skipped: list[str])`. `flagged` holds the addresses of `no_text` and `withheld` passages; `skipped` holds `"<doc_id>@<rev>: <reason>"`.
  - `ingest_pack(pack: Pack, store: Store) -> IngestReport`. Skip reasons: `"file missing"`, `"no checksum recorded; run fetch"`, `"checksum mismatch"`. A skipped document is not written to the store.

- [ ] **Step 1: Write the failing tests**
  - `test_ingest_offline_pack_counts`: `report.documents == 4`, and `"SYN-RG1@r1#p3.1"` is in `report.flagged`, as is the withheld passage address
  - `test_passage_roundtrip`: `store.passage(a) == p` for a passage read in Task 2
  - `test_documents_status_filter`: the issued documents are `SYN-RG1@r1`, `SYN-SAR@r2` and `SYN-SE@r1`
  - `test_ingest_skips_checksum_mismatch` (Review Focus 3): append a byte to `source/SYN-SE@r1.pdf`. The report's `skipped` contains `"SYN-SE@r1: checksum mismatch"`, and `store.document("SYN-SE", "r1") is None`.
  - `test_ingest_skips_missing_checksum`: with an empty `sha256`, the skip reason is `"no checksum recorded; run fetch"`
  - `test_reingest_replaces_passages`: two ingests give the same passage count
  - `test_fts_search_excludes_superseded`: `fts_search('"temperature"', False, 10)` returns only `SYN-SAR@r2` addresses; with `True` it includes `@r1`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_store_ingest.py -q` → FAIL.
- [ ] **Step 3: Implement `store.py` and `ingest.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: SQLite store with FTS5 and checksum-checked ingest`).

---

### Task 4: Fetch and the network guard

**Files:**
- Create: `src/goldthread/fetch.py`, `src/goldthread/netguard.py`
- Test: `tests/test_fetch.py` (fixture `online_pack`: a copy of the synthetic pack with `offline: false`, one register row `DOC-A@r1` with `url: https://example.invalid/a.pdf`)

**Interfaces:**
- Consumes: `Pack`, `update_register_checksum`, `source_path`
- Produces:
  - `USER_AGENT = "golden-thread/0.1"`
  - `http_get(url: str, timeout: float = 60.0) -> bytes`, using `urllib.request` with the `User-Agent` header
  - `class OfflineError(Exception)`
  - `FetchReport(downloaded: list[str], recorded_checksums: list[str], mismatched: list[str], already_present: list[str])`
  - `fetch_pack(pack: Pack, opener: Callable[[str], bytes] = http_get) -> FetchReport`:
    - Raises `OfflineError("offline pack: fetch is disabled")` when `pack.offline`.
    - A cached file matching the register `sha256` goes in `already_present`.
    - A cached file with an empty register `sha256` has its checksum recorded, and goes in `recorded_checksums` and `already_present`. This is how user-uploaded files get registered.
    - Otherwise the file is downloaded. If the register `sha256` is empty, the checksum is recorded. If the downloaded bytes don't match a non-empty `sha256`, they are written to `cache/quarantine/<doc_id>@<rev>.pdf` and the doc goes in `mismatched`.
  - `class NetworkBlocked(RuntimeError)`
  - `no_network() -> ContextManager[None]`: patches `socket.socket.connect`, `socket.create_connection` and `socket.getaddrinfo` to raise `NetworkBlocked`, and restores them on exit

- [ ] **Step 1: Write the failing tests**
  - `test_fetch_downloads_and_records_checksum`: with the opener returning `b"%PDF-1.4 a"`, `downloaded == ["DOC-A@r1"]` and the register `sha256` equals `hashlib.sha256(b"%PDF-1.4 a").hexdigest()`
  - `test_fetch_registers_uploaded_file`: with the file already in the cache and the register empty, the doc is in `recorded_checksums` and the opener is never called
  - `test_refetch_checksum_mismatch_quarantined` (Review Focus 3): with the register `sha256` set for other bytes and no cached file, `mismatched == ["DOC-A@r1"]`, the quarantine file exists and `cache/DOC-A@r1.pdf` does not
  - `test_fetch_refused_for_offline_pack`: `pytest.raises(OfflineError, match="offline pack: fetch is disabled")`
  - `test_no_network_blocks_and_restores`: inside the context, `socket.create_connection(("example.com", 80))` raises `NetworkBlocked`; after it, `socket.create_connection is` the original
  - `test_http_get_sends_generic_user_agent`: monkeypatch `urllib.request.urlopen` and assert the request header `User-agent == "golden-thread/0.1"`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_fetch.py -q` → FAIL.
- [ ] **Step 3: Implement `fetch.py` and `netguard.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: fetch with checksum recording and quarantine; no_network guard`).

---

### Task 5: Aliases and search

**Files:**
- Create: `src/goldthread/aliases.py`, `src/goldthread/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `Store.fts_search`, `Passage`
- Produces:
  - `AliasTable.from_csv(path: Path) -> AliasTable`. Each canonical term is also its own variant.
    - `find(text: str) -> list[str]`: canonical terms with a variant occurring in `text`, case-insensitive, whitespace- and hyphen-insensitive, with word boundaries on both sides
    - `variants(canonical: str) -> list[str]`
    - `canonical(term: str) -> str | None`
  - `Hit(passage: Passage, score: float)` (frozen)
  - `STOPWORDS: frozenset[str]` (about 100 common English words)
  - `find_identifiers(text: str) -> list[str]`: matches of `r"\d+(?:\.\d+)+(?:\([a-z0-9]+\))*"` and `r"\bML\d{5}[A-Z]\d{3}\b"`
  - `build_match_expr(question: str, aliases: AliasTable) -> str`: an FTS5 OR expression of quoted phrases. Each identifier is a phrase of its alphanumeric tokens; each variant of every alias found is a phrase; each remaining word of 3 or more letters not in `STOPWORDS` is a term. Returns `""` when there is nothing.
  - `search(store: Store, aliases: AliasTable, question: str, k: int = 10, include_superseded: bool = False) -> list[Hit]`. Returns `[]` for an empty expression. It fetches `k * 5` candidates. When the question has identifiers or aliases, it keeps only passages whose `heading + "\n" + text` contains at least one of them (an identifier, or a variant of an alias found in the question) as an exact case-insensitive substring after whitespace collapse. It skips `no_text` passages and returns the top `k`.

- [ ] **Step 1: Write the failing tests** (on the ingested synthetic store and `pack.aliases_path`)
  - `test_alias_find_and_variants`: `find("Does the design meet Criterion 10?") == ["PDC 10"]`, and the variants are `{"PDC 10", "Criterion 10", "MHTGR-DC 10"}`
  - `test_alias_word_boundary`: `find("PDC 100") == []`, `find("PDC 1") == []`
  - `test_search_uses_aliases`: the hits for `"How is PDC 10 met?"` include the passage containing `"meets Criterion 10"`
  - `test_superseded_excluded_by_default`: every hit for `"fuel temperature limit"` is in `SYN-SAR@r2` or another issued doc, never `@r1`; with `include_superseded=True` some hit is in `@r1`
  - `test_identifier_near_miss_excluded` (Review Focus 1): for `"What does 50.34(a) require?"`, every hit's text contains `"50.34(a)"` and the `"50.34(b)"` passage is absent
  - `test_stopwords_only_returns_empty`: `search(..., "the of and") == []`
  - `test_k_limit`: `len(search(..., "fuel", k=1)) == 1`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_search.py -q` → FAIL.
- [ ] **Step 3: Implement `aliases.py` and `search.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: alias table and keyword search with exact identifiers`).

---

### Task 6: Quote verifier

**Files:**
- Create: `src/goldthread/verifier.py`
- Test: `tests/test_verifier.py`

**Interfaces:**
- Consumes: `Store.passage`, `Store.document`
- Produces:
  - `Verification(ok: bool, reason: str = "")` (frozen)
  - `normalise(text: str, join_hyphenation: bool) -> str`:
    - NFKC
    - `‘ ’ ‚ ′` → `'`; `“ ” „ ″` → `"`; `– — ‑ ‒ −` → `-`
    - if `join_hyphenation`, `-\n` → `""`
    - whitespace collapsed to single spaces, then stripped
  - `verify_quote(store: Store, address: str, quote: str) -> Verification`. Reasons, in order: `"empty quote"`, `"unknown address"`, `"cited revision is superseded"`, `"quote not found in passage"`. It passes if `normalise(quote, False)` is a substring of the passage text normalised either with or without hyphenation joining.

- [ ] **Step 1: Write the failing tests**
  - `test_exact_quote_passes`: the `"The fuel temperature limit is 1650 C."` passage verifies
  - `test_line_breaks_and_spaces`: a quote spanning the wrapped lines of the Criterion 10 paragraph, written with single spaces, verifies
  - `test_normalise_hyphenation`: `normalise("contain-\nment", True) == "containment"` and `normalise("pebble-\nbed", False) == "pebble- bed"`
  - `test_curly_quotes_and_dashes`: `normalise("the ‘core’ – limit", False) == "the 'core' - limit"`
  - `test_quote_not_in_passage` returns reason `"quote not found in passage"`
  - `test_cross_passage_quote_fails`: the end of one passage plus the start of the next, cited to the first, fails
  - `test_superseded_revision_fails`: the `SYN-SAR@r1` address returns reason `"cited revision is superseded"`
  - `test_unknown_address` and `test_empty_quote` return their reasons
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_verifier.py -q` → FAIL.
- [ ] **Step 3: Implement `verifier.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: deterministic quote verifier`).

---

### Task 7: Prices, ledger and budget guard

**Files:**
- Create: `src/goldthread/prices.yaml`, `src/goldthread/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `Usage`, `Budget`, `Pack`, `PackError`, `HOSTED_PROVIDERS`
- Produces:
  - `prices.yaml` (USD per million tokens), with `checked: 2026-11-21` and `source: https://platform.claude.com/docs/en/about-claude/pricing`:

    | model | input | output | cache_read | cache_write |
    |---|---|---|---|---|
    | claude-opus-5-5 | 4.00 | 20.00 | 0.20 | 5.00 |
    | claude-opus-5 | 5.00 | 25.00 | 0.50 | 6.25 |
    | claude-opus-4-8 | 5.00 | 25.00 | 0.50 | 6.25 |
    | claude-sonnet-5-5 | 2.00 | 10.00 | 0.10 | 2.50 |

  - `Price(input: float, output: float, cache_read: float, cache_write: float)`
  - `PriceTable(prices: Mapping[str, Price])`
    - `.load(path: Path = PRICES_PATH) -> PriceTable`
    - `.get(model: str) -> Price | None`
    - `.most_expensive() -> Price` (the highest output price)
  - `worst_case_cost(price: Price, input_tokens: int, max_output_tokens: int) -> float`
  - `actual_cost(price: Price, usage: Usage) -> float` (input, output, cache read and cache write, each at its own rate)
  - `SpendEntry(run_id, ts, job, model_requested, served_by, hosted: bool, input_tokens, output_tokens, cache_read, cache_write, cost_usd, price_assumed: bool, fallback: bool, duration_s: float)`
  - `Ledger(path: Path)`, stored in SQLite at `pack.data_dir/"ledger.sqlite3"`
    - `record(entry: SpendEntry) -> None`
    - `run_total(run_id: str) -> float`
    - `month_total(year_month: str) -> float` (`"YYYY-MM"`, UTC)
    - `entries(run_id: str) -> list[SpendEntry]`
  - `class BudgetExceeded(Exception)` with attributes `limit: str` (`"run"` or `"month"`), `needed_usd: float`, `remaining_usd: float`
  - `BudgetGuard(budget: Budget, ledger: Ledger, prices: PriceTable, run_id: str, now: Callable[[], datetime] = utc_now)`
    - `check(job: str, model: str, hosted: bool, input_tokens: int, max_output_tokens: int) -> None`: zero cost when not `hosted`; raises `BudgetExceeded` when the run total plus the worst case would exceed the run limit, checked before the month limit
    - `record(job: str, model_requested: str, served_by: str, hosted: bool, usage: Usage, fallback: bool, duration_s: float) -> SpendEntry`: priced at the max of the requested and serving models' prices; an unknown serving model gets `most_expensive()` and `price_assumed=True`
  - `validate_prices(pack: Pack, prices: PriceTable) -> None`: raises `PackError("no price for model '<m>'")` for any hosted job model missing from the table
  - `RunCostSummary(run_id, per_job_model: dict[tuple[str, str], tuple[int, int, float]], run_usd: float, month_usd: float, month_remaining_usd: float)`
  - `summarise(ledger: Ledger, budget: Budget, run_id: str, now: Callable[[], datetime] = utc_now) -> RunCostSummary`
  - `render_cost_summary(s: RunCostSummary) -> str`

- [ ] **Step 1: Write the failing tests**
  - `test_worst_case_cost`: `worst_case_cost(Price(4,20,0.2,5), 100_000, 16_000) == pytest.approx(0.72)`
  - `test_actual_cost_with_cache`: `Usage(1000, 500, 2000, 1000)` → `pytest.approx(0.0194)`
  - `test_guard_stops_before_run_limit`: with budget `Budget(1.0, 100)`, 0.5 already recorded for the run, and a check worth 0.72, it raises `BudgetExceeded` with `limit == "run"`, `remaining_usd == pytest.approx(0.5)` and `needed_usd == pytest.approx(0.72)`
  - `test_guard_month_limit_spans_runs`: two runs in the same month together hit the month limit
  - `test_month_boundary`: an entry at `2026-10-31T23:59:59Z` isn't counted in `month_total("2026-11")`
  - `test_unknown_served_model_priced_conservatively` (Review Focus 5): requested `claude-opus-5-5`, served `claude-mystery` → the cost uses `most_expensive()`, with `price_assumed` and `fallback` both True
  - `test_fallback_uses_max_price`: requested `claude-sonnet-5-5`, served `claude-opus-4-8` → priced at the Opus 4.8 rate
  - `test_local_costs_zero_records_tokens`: `hosted=False` → `cost_usd == 0`, with the tokens and `duration_s` stored
  - `test_validate_prices_rejects_unknown_hosted_model` raises `PackError` "no price for model 'claude-unknown'"
  - `test_summary_and_render`: the per-job/model totals, month totals and remaining amount render in the text
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_budget.py -q` → FAIL.
- [ ] **Step 3: Implement `prices.yaml` and `budget.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: price table, spend ledger and budget guard`).

---

### Task 8: Connector interface and the fake connector

**Files:**
- Create: `src/goldthread/models/__init__.py`, `src/goldthread/models/base.py`, `src/goldthread/models/fake.py`
- Test: `tests/test_fake_connector.py`

**Interfaces:**
- Consumes: `ModelSpec`, `Passage`, `Usage`, `Pack`, `PackError`
- Produces (`base.py`, all frozen):
  - `NOT_FOUND = "NOT_FOUND"`
  - `Prompt(system: str, user_text: str, passages: tuple[Passage, ...] = (), titles: Mapping[str, str] = {}, schema: Mapping | None = None)`. `titles` maps an address to the source title shown to the model.
  - `RawCitation(address: str, quote: str)`
  - `RawBlock(text: str, citations: tuple[RawCitation, ...])`
  - `RawAnswer(blocks: tuple[RawBlock, ...], stop_reason: str, served_by: str, fallback: bool, usage: Usage)`
  - `RawStructured(data: Mapping, stop_reason: str, served_by: str, fallback: bool, usage: Usage)`
  - `Connector` (Protocol): attributes `provider: str`, `hosted: bool`; methods
    - `estimate_input_tokens(spec: ModelSpec, prompt: Prompt) -> int`
    - `answer(spec: ModelSpec, prompt: Prompt) -> RawAnswer`
    - `structured(spec: ModelSpec, prompt: Prompt) -> RawStructured`
- Produces (`fake.py`): `FakeConnector(script: Mapping[str, object] = {}, extractions: Mapping[str, list[dict]] = {}, hosted: bool = False, provider: str = "fake")`
  - `answer`:
    - If `prompt.user_text` is in `script`, it returns the scripted value: `"NOT_FOUND"` gives one block with text `NOT_FOUND`; `"REFUSE"` gives `stop_reason="refusal"` and no blocks; a list of `RawBlock` is returned as is.
    - Otherwise it makes one block per passage (up to 2) with `kind == "text"`: text and quote are both the passage's first sentence (split on `(?<=[.!?])\s`).
  - `structured`:
    - If `prompt.schema` has a `"verdict"` property, the verdict is `"yes"` when every word of the expected point (the line after `EXPECTED:` in `user_text`) appears in the line after `ANSWER:` (case-insensitive); otherwise `"no"`.
    - Otherwise it returns `{"records": extractions.get(chunk_id, [])}`, where `chunk_id` is the text after `CHUNK: ` on the first line of `user_text`.
  - Usage is `len(text) // 4` tokens each way, and `served_by` is `spec.model`.
- Produces (`models/__init__.py`): `get_connector(provider: str, pack: Pack | None = None, client: object | None = None) -> Connector`
  - `"fake"` → `FakeConnector(extractions=yaml.safe_load(pack.root/"fake_extractions.yaml"))` if that file exists
  - `"claude"` → `ClaudeConnector(client)` (Task 10; import it lazily)
  - anything else → `PackError("unknown provider '<p>'")`

- [ ] **Step 1: Write the failing tests**
  - `test_default_answer_cites_first_sentence`: for two text passages, the two blocks each have `citations[0].quote` equal to the block text and taken from that passage
  - `test_script_not_found_and_refuse`
  - `test_structured_extraction_by_chunk`: `user_text` beginning `"CHUNK: X@r1#0\n"` returns the extractions for `X@r1#0`
  - `test_structured_judge`: a schema with `verdict`, `EXPECTED: 1650` and `ANSWER: limit is 1650 C` gives `{"verdict": "yes", ...}`
  - `test_get_connector_unknown` raises `PackError`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_fake_connector.py -q` → FAIL.
- [ ] **Step 3: Implement `base.py`, `fake.py` and `get_connector`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: connector interface and deterministic fake connector`).

---

### Task 9: Answerer, audit log and rendering

**Files:**
- Create: `src/goldthread/answerer.py`, `src/goldthread/audit.py`, `src/goldthread/render.py`
- Test: `tests/test_answerer.py`

**Interfaces:**
- Consumes: `search`, `verify_quote`, `BudgetGuard`, `Connector`, `Prompt`, `NOT_FOUND`, `Store`, `AliasTable`, `Pack`
- Produces:
  - `AuditLog(path: Path)` with `write(event: str, **fields) -> None`: one JSON line containing `ts` (UTC ISO 8601), `event` and the fields
  - `CheckedCitation(address: str, quote: str, ok: bool, reason: str)`
  - `Statement(text: str, citations: tuple[CheckedCitation, ...], status: str)`, where `status` is `verified`, `flagged`, `unsourced` or `connective`
  - `Answer(question, kind, statements, searched: tuple[str, ...], hits: tuple[str, ...], model, served_by, run_id, cost_usd)`, where `kind` is `answer`, `not_found` or `refused`, and `searched` holds `"doc_id@rev — title"` for every issued document
  - `UNSOURCED_MIN_CHARS = 25`
  - `ANSWER_SYSTEM`: fixed instructions, followed by the pack's `rules` and `answer_format`. They must say:
    - answer only from the provided search results;
    - every sentence that states a fact must be supported by citations;
    - if the results don't answer the question, reply with exactly `NOT_FOUND`;
    - never guess text that is marked withheld;
    - always state any conditions attached to a finding.
  - `ask(pack, store, aliases, connector, spec, guard, audit, question: str, run_id: str, k: int = 10) -> Answer`:
    - No hits → `not_found` with **no model call**.
    - Otherwise it builds `Prompt(system, question, passages, titles)` (title: `"<doc title> — <heading>"`), calls `guard.check` with `connector.estimate_input_tokens`, calls the model, then `guard.record`.
    - A reply that is only `NOT_FOUND` → `not_found`; `stop_reason == "refusal"` → `refused`.
    - Each block becomes a `Statement`: with citations, it's `verified` only if every citation passes `verify_quote`, otherwise `flagged`; without citations, it's `unsourced` if its stripped length is at least 25, otherwise `connective`.
    - It writes one audit event `"ask"` with the question, hit addresses, kind, model, served_by, statement statuses and citation results.
  - `render_answer_md(answer: Answer, outside: str = "") -> str` and `render_answer_html(answer: Answer, outside: str = "") -> str` (HTML-escaped):
    - a verified statement shows its text, then each citation as `` `address` `` and the quote in quotation marks;
    - a flagged statement is prefixed `⚠` and shows the reason;
    - an unsourced statement is prefixed `⚠ no source:`;
    - `not_found` renders `Not found. Searched:` followed by the list, plus `Outside this corpus:` and `outside` when given;
    - `refused` renders `The model declined to answer (refusal). This is not a "not found" result.`

- [ ] **Step 1: Write the failing tests** (synthetic store, `FakeConnector`, real `BudgetGuard` with a temporary ledger)
  - `test_answer_verified_statements`: for `"What is the fuel temperature limit?"`, `kind == "answer"`, every statement is `verified`, and every citation address starts with `SYN-SAR@r2` or another issued doc
  - `test_no_hits_not_found_without_model_call`: with a spy connector, `ask(..., "zzzz qqqq")` gives `kind == "not_found"` and 0 calls; `searched` contains `"SYN-SAR@r2 — "` and no `@r1`
  - `test_model_not_found_sentinel`: a scripted `NOT_FOUND` gives `not_found` with `searched` filled
  - `test_flagged_quote_shown_with_reason`: a scripted block whose quote isn't in the passage gives `flagged`, with reason `"quote not found in passage"`; the Markdown contains `⚠`
  - `test_unsourced_and_connective`: `"Based on the results:"` is `connective`, and `"The limit was raised in a later revision of the report."` is `unsourced`
  - `test_refusal_is_not_not_found` (Review Focus 5): a scripted `REFUSE` gives `kind == "refused"`, and the Markdown contains "not a \"not found\" result"
  - `test_budget_stop_raises_before_call`: with `FakeConnector(hosted=True)`, a price table `{"fake": Price(1000, 1000, 0, 0)}` and a budget of 0.01, it raises `BudgetExceeded` and the connector is never called
  - `test_audit_line_written`: the last line parses to `event == "ask"` with `hits` and `kind`
  - `test_render_html_escapes`: the text `<b>` renders as `&lt;b&gt;`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_answerer.py -q` → FAIL.
- [ ] **Step 3: Implement `audit.py`, `answerer.py` and `render.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: answerer with verified citations, not-found scope, audit log and rendering`).

---

### Task 10: Claude connector

**Files:**
- Create: `src/goldthread/models/claude.py`
- Test: `tests/test_claude_connector.py` (a stub client: `client.beta.messages.create(**kw)` records `kw` and returns a `SimpleNamespace` response; `client.messages.count_tokens(**kw)` returns `SimpleNamespace(input_tokens=1234)`)

**Interfaces:**
- Consumes: `Connector`, `Prompt`, `Raw*`, `ModelSpec`, `Usage`
- Produces: `FALLBACK_BETA = "server-side-fallback-2026-07-01"`; `ClaudeConnector(client=None)` with `provider = "claude"`, `hosted = True`. A `client` of `None` creates `anthropic.Anthropic()` on first use.
  - `answer(spec, prompt)` calls `client.beta.messages.create` with exactly these keyword arguments:
    - `model=spec.model`, `max_tokens=spec.max_tokens`
    - `betas=[FALLBACK_BETA]`, `fallbacks="default"`
    - `output_config={"effort": spec.effort}`
    - `system=prompt.system`
    - `messages=[{"role": "user", "content": [*search_result blocks, {"type": "text", "text": prompt.user_text}]}]`
    
    Each passage becomes `{"type": "search_result", "source": p.address, "title": prompt.titles[p.address], "content": [{"type": "text", "text": p.text}], "citations": {"enabled": True}}`. Passages with empty text are skipped.
  - Reading the answer response:
    - Each `content` block with `type == "text"` becomes a `RawBlock`. Its `citations` (`block.citations or []`) of `type == "search_result_location"` become `RawCitation(c.source, c.cited_text)`.
    - A block with `type == "fallback"` sets `fallback=True`; every other block type is ignored.
    - `served_by=response.model` and `stop_reason=response.stop_reason`.
    - Usage comes from `response.usage`, with missing or `None` cache fields read as 0.
  - `structured(spec, prompt)` calls `client.beta.messages.create` with:
    - `model`, `max_tokens`, `betas`, `fallbacks` as above
    - `output_config={"effort": spec.effort, "format": {"type": "json_schema", "schema": dict(prompt.schema)}}`
    - `system=[{"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}]`
    - `messages=[{"role": "user", "content": prompt.user_text}]`
    
    The data is `json.loads` of the first `text` block. With `stop_reason == "refusal"` the data is `{}`.
  - `estimate_input_tokens(spec, prompt)`: `client.messages.count_tokens(model=spec.model, system=<as sent>, messages=<as sent>).input_tokens`, plus `len(json.dumps(prompt.schema)) // 3` when a schema is present

- [ ] **Step 1: Write the failing tests**
  - `test_answer_request_shape`: asserts every keyword above; `"format" not in kw["output_config"]`; none of `temperature`, `top_p`, `top_k` is in `kw`; the first content block equals the expected `search_result` dict and the last is the question text block
  - `test_answer_parses_citations`: a response with a thinking block, a text block with one `search_result_location` citation and an uncited text block gives two `RawBlock`s, and the first has `RawCitation(addr, cited)`
  - `test_fallback_block_sets_served_by_and_flag` (Review Focus 5): a `fallback` block plus `response.model == "claude-opus-4-8"` gives `fallback is True` and `served_by == "claude-opus-4-8"`
  - `test_refusal_passthrough`: `stop_reason == "refusal"` gives no blocks for `answer` and `{}` for `structured`
  - `test_structured_request_shape`: `output_config == {"effort": "low", "format": {"type": "json_schema", "schema": schema}}`; `system[0]["cache_control"] == {"type": "ephemeral"}`; there is no `search_result` anywhere in `messages`
  - `test_structured_parses_json`
  - `test_estimate_adds_schema_overhead`: `== 1234 + len(json.dumps(schema)) // 3`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_claude_connector.py -q` → FAIL.
- [ ] **Step 3: Implement `claude.py`.** Check the request shapes against the claude-api skill's Python docs before writing.
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: Claude connector with search-result citations, structured output and fallbacks`).

---

### Task 11: Records, extraction and linking

**Files:**
- Create: `src/goldthread/records.py`, `src/goldthread/extractor.py`, `src/goldthread/linker.py`, `tests/fixtures/packs/synthetic/fake_extractions.yaml`
- Modify: `src/goldthread/store.py` (record, link and progress methods)
- Test: `tests/test_extract_link.py`

**Interfaces:**
- Consumes: `RecordSchema`, `LayoutRecipe`, `Record`, `Link`, `Store`, `Connector`, `BudgetGuard`, `BudgetExceeded`, `verify_quote`, `AliasTable`, `AuditLog`
- Produces (`store.py` additions):
  - `upsert_record(rec: Record) -> None`: an existing record with status `verified`, `corrected` or `rejected` is left unchanged
  - `record(id: str) -> Record | None`
  - `records(type: str | None = None) -> list[Record]`
  - `set_review(id: str, status: str, reviewer: str, at: str, fields: Mapping[str, str] | None, quote: str | None, flags: tuple[str, ...]) -> None`
  - `add_link(link: Link) -> None` (idempotent)
  - `links(src: str | None = None, dst: str | None = None, link_type: str | None = None) -> list[Link]`
  - `mark_chunk_done(run_id: str, chunk_id: str) -> None` and `chunks_done(run_id: str) -> set[str]`
- Produces (`records.py`):
  - `record_id(rt: RecordType, address: str, quote: str) -> str`: `f"{rt.prefix}-{sha1(f'{rt.name}|{address}|{quote}').hexdigest()[:8]}"`
  - `extraction_schema(schema: RecordSchema, looks_for: Sequence[str], addresses: Sequence[str]) -> dict`. A JSON schema for `{"records": [{"type", "key", "address", "quote", "fields": [{"name", "value"}]}]}` with:
    - `type` an enum of `looks_for`;
    - `address` an enum of `addresses`;
    - `fields[].name` an enum of the union of those types' fields;
    - `additionalProperties: false` and every property required at each object level.
  - `missing_required(rt: RecordType, fields: Mapping[str, str]) -> list[str]`
- Produces (`extractor.py`):
  - `Chunk(id: str, doc_id: str, revision: str, heading: str, passages: tuple[Passage, ...])`
  - `make_chunks(passages: Sequence[Passage], max_chars: int = 12000) -> list[Chunk]`: consecutive passages of one document grouped by top-level heading, split when they would exceed `max_chars`; ids are `"<doc_id>@<rev>#<index>"`; `no_text` passages are excluded
  - `EXTRACT_SYSTEM`: fixed instructions followed by the layout's `instructions` and `example`. They must say:
    - extract only the listed record types;
    - each record's `quote` is copied verbatim from the passage named in `address`;
    - use `key` values `k1`, `k2`, … unique within the chunk for cross-references;
    - leave a field empty rather than guess;
    - never infer withheld text.
  - The user text is `CHUNK: <id>\nDOCUMENT: <title> (<doc_id>@<rev>)\nSECTION: <heading>\n\n`, then `[<address>]\n<text>\n\n` for each passage.
  - `ExtractReport(run_id, chunks_total: int, chunks_done: int, records_new: int, records_flagged: int, stopped: str | None, remaining_chunks: list[str])`
  - `extract_pack(pack, store, connector, spec, guard, audit, run_id: str, resume: bool = False, only_docs: Sequence[str] = ()) -> ExtractReport`. It works through issued documents whose layout has a recipe, in register order.
    - Chunks already done for `run_id` are skipped when `resume`.
    - For each chunk: `guard.check` → `connector.structured` → `guard.record` → each returned record is stored as `draft` with `chunk_id`, `extracted_by=served_by` and `run_id`.
    - Flags: `"quote_failed: <reason>"` from `verify_quote`, and `"missing_field: <name>"`.
    - Then the chunk is marked done.
    - `BudgetExceeded` stops the run with `stopped = f"budget: {limit} limit"` and fills `remaining_chunks`.
    - An audit event `"extract_chunk"` is written per chunk.
- Produces (`linker.py`):
  - `LinkReport(created: int, unresolved: list[str])`
  - `link_records(store: Store, schema: RecordSchema, aliases: AliasTable) -> LinkReport`. For each link type and each source record with a non-empty `field`:
    - with scope `chunk`, it matches target records in the same `chunk_id` whose target field equals the value;
    - with scope `code`, it matches target records whose target field has the same canonical alias (`aliases.canonical(v) or v`, compared case-insensitively).
    
    `reverse` swaps the stored `src`/`dst`. Values that match nothing are listed in `unresolved` as `"<record id>.<field>=<value>"`.

`fake_extractions.yaml` holds the records for the synthetic chunks. All quotes are taken from the Task 2 sentences except the deliberate bad one:
- `SYN-RG1@r1#0` (the "1 Scope" section): no records
- `SYN-RG1@r1#1` (the "2 Criteria" section): two `Requirement`s, code `Criterion 10` (text from the Criterion 10 sentence) and code `Criterion 11`
- `SYN-SAR@r2#0`:
  - `Claim` k1 (`requirement_code: PDC 10`)
  - `Argument` k2 (`claim_key: k1`, `method_code: ""`)
  - `EvidenceRef` k3 (`argument_key: k2`, `reference: TR-123`, `available: no`)
  - `Claim` k4 with a deliberately bad quote
- `SYN-SE@r1#0`: `Finding` k1 (`subject_code: MHTGR-DC 10`) and `Condition` (`finding_key: k1`)

- [ ] **Step 1: Write the failing tests**
  - `test_make_chunks_never_mix_documents_and_respect_size`
  - `test_extraction_schema_enums`: the `type` enum equals `looks_for`, the `address` enum equals the chunk's addresses, and every object has `additionalProperties` False
  - `test_extract_creates_drafts_and_flags_bad_quote`: all records are `draft`; the k4 claim has the flag `"quote_failed: quote not found in passage"`; the others have no flags
  - `test_missing_required_field_flagged`
  - `test_ids_stable_and_review_preserved`: after `set_review(..., "verified", ...)` and a re-run, the record is still `verified` and the record count is unchanged
  - `test_extract_budget_stop_and_resume`: a hosted fake with a high price and a tiny budget stops with `stopped == "budget: run limit"` and `remaining_chunks` non-empty; resuming the same `run_id` with a larger budget gives `remaining_chunks == []`, and every record id is unique
  - `test_only_docs_filter`
  - `test_linker_code_scope_uses_aliases`: there is a `Link(CLM-…, "meets", REQ-…)` for the `Criterion 10` requirement, and the `Finding` (`MHTGR-DC 10`) has an `evaluates` link to the same requirement
  - `test_linker_chunk_scope_and_reverse`: there is a `Link(ARG-…, "cites", EVD-…)`
  - `test_unresolved_links_reported`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_extract_link.py -q` → FAIL.
- [ ] **Step 3: Implement the store additions, `records.py`, `extractor.py`, `linker.py` and the fixture.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: record extraction with resume, quote checks and alias-aware linking`).

---

### Task 12: Review export and import

**Files:**
- Create: `src/goldthread/review.py`
- Test: `tests/test_review.py`

**Interfaces:**
- Consumes: `Store` record methods, `verify_quote`
- Produces:
  - `REVIEW_COLUMNS = ["id", "type", "status", "address", "quote", "fields_json", "quote_check", "decision", "corrected_fields_json", "corrected_quote", "note"]`
  - `export_review(store: Store, path: Path, statuses: Sequence[str] = ("draft",)) -> int`: written as UTF-8 with BOM (`utf-8-sig`); `quote_check` is `ok` or the failure reason; returns the row count
  - `ImportReport(applied: int, rejected_rows: list[str], reverified_failed: list[str])`
  - `import_review(store: Store, path: Path, reviewer: str, now: Callable[[], datetime] = utc_now) -> ImportReport`:
    - columns are found by header name, in any order; read as `utf-8-sig`;
    - decisions are `verified`, `corrected`, `rejected` or blank (skipped);
    - `corrected` applies `corrected_fields_json` (a JSON object) and/or `corrected_quote`, then re-verifies the quote; on failure the record stays `draft` with a `quote_failed` flag and is listed in `reverified_failed`;
    - unknown ids, invalid JSON or an unknown decision go in `rejected_rows` as `"row <n>: <reason>"`.

- [ ] **Step 1: Write the failing tests**
  - `test_export_bom_header_and_rows`: the bytes start with `b"\xef\xbb\xbf"`, the header equals `REVIEW_COLUMNS`, and the row count equals the number of draft records
  - `test_import_verified_sets_reviewer_and_time`
  - `test_import_rejected`
  - `test_import_excel_bom_reordered_columns_and_edited_quote` (Review Focus 2): rewrite the sheet with the columns reversed and a BOM, and mark one row `corrected` with a `corrected_quote` that isn't in the source. The `reverified_failed` list holds that id, and the record is `draft` with a flag starting `quote_failed`.
  - `test_import_unknown_id_and_bad_json_reported`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_review.py -q` → FAIL.
- [ ] **Step 3: Implement `review.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: review sheet export and import with re-verification`).

---

### Task 13: Trace and checks

**Files:**
- Create: `src/goldthread/trace.py`, `src/goldthread/checks.py`
- Test: `tests/test_trace_checks.py`

**Interfaces:**
- Consumes: `Store` records and links, `AliasTable`, `RecordSchema`, `CoverageRule`
- Produces:
  - `TraceNode(record: Record, via: str, children: list[TraceNode])`, where `via` is `"<- meets"`, `"-> cites"` and so on
  - `trace(store: Store, aliases: AliasTable, start: str, max_depth: int = 4) -> list[TraceNode]`:
    - `start` is a record id, or a code matched against every record's `code` field by canonical alias;
    - it walks links breadth-first in both directions without revisiting, children sorted by `(via, id)`;
    - it returns `[]` when nothing matches.
  - `render_trace_md(nodes: list[TraceNode], searched: Sequence[str]) -> str`:
    - one nested list item per record: `type id [status]`, `` `address` ``, the quote in quotation marks, and key fields;
    - an `EvidenceRef` shows `cited, not available in this pack`;
    - a `draft` record shows `(draft, not yet reviewed)`;
    - no match renders `Not found. Searched:` with the list.
  - `CheckReport(coverage: dict[str, list[str]], superseded_citations: list[str])`:
    - each coverage rule name maps to the matching record ids:
      - `missing_incoming`: no incoming link of that type;
      - `has_incoming`: at least one incoming link of that type;
      - `has_outgoing`: at least one outgoing link of that type;
    - `superseded_citations` lists records whose address is in a superseded document.
  - `run_checks(store: Store, schema: RecordSchema) -> CheckReport`
  - `render_checks_md(report: CheckReport) -> str`

- [ ] **Step 1: Write the failing tests** (after the Task 11 extraction and linking on the synthetic store)
  - `test_trace_from_alias_code`: the Markdown for `trace(..., "PDC 10")` contains the ids of the REQ, CLM, ARG, EVD, FND and CND records, the text `cited, not available in this pack`, and `(draft, not yet reviewed)`
  - `test_trace_unknown_code`: `render_trace_md([], searched)` starts with `Not found. Searched:`
  - `test_coverage_rules`: `"Requirements with no claim"` lists the `Criterion 11` requirement; `"Findings with conditions"` lists the finding; `"Arguments citing evidence not loaded"` lists the argument
  - `test_superseded_citations`: a record inserted with an `SYN-SAR@r1` address is listed
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_trace_checks.py -q` → FAIL.
- [ ] **Step 3: Implement `trace.py` and `checks.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: requirement trace and coverage checks`).

---

### Task 14: Evaluation runner

**Files:**
- Create: `src/goldthread/evaluate.py`
- Modify: synthetic `tests.csv`, which holds:
  - `q1`: approved, "What is the fuel temperature limit?", sources `SYN-SAR@r2`, point `1650`
  - `q2`: approved, "Which seismic isolation bearings are specified?", `expect_not_found` yes (none of its words occur in the synthetic documents)
  - `q3`: approved, "What does 50.34(a) require?", sources `SYN-SAR@r2`, point `preliminary safety analysis report`
  - `q4`: draft, any question
- Test: `tests/test_evaluate.py`

**Interfaces:**
- Consumes: `ask`, `search`, `verify_quote`, `Connector`, `BudgetGuard`, `AuditLog`, `pack_version`, `summarise`
- Produces:
  - `SUCCESS_THRESHOLDS = {"retrieval_hit_rate": 0.80, "not_found_accuracy": 1.0, "verified_quote_integrity": 1.0}`
  - `JUDGE_SYSTEM`: fixed text: "Grade whether the answer covers the expected key point. Reply with verdict yes, partial or no and a one-sentence reason." The judge user text is `QUESTION: …\nEXPECTED: …\nANSWER: …`, with the schema `{"verdict": enum[yes, partial, no], "reason": string}`.
  - `CaseResult(id, status, answer_kind, retrieval_hit: bool | None, expected_cited: bool | None, not_found_ok: bool, quotes_total: int, quotes_verified: int, judge: str)`
  - `EvalReport(run_id, pack_version, models: dict[str, str], results: list[CaseResult], metrics: dict[str, float], passed: bool, stopped: str | None, remaining: list[str])`
  - `run_eval(pack, store, aliases, connectors: Mapping[str, Connector], guard, audit, run_id: str, resume: bool = False) -> EvalReport`:
    - Metrics cover approved cases only. Drafts are run and listed, but excluded.
    - `retrieval_hit`: any expected source is a prefix of a top-10 hit address.
    - `expected_cited`: any citation address starts with an expected source.
    - `not_found_ok`: `expect_not_found` matches whether the answer `kind` is `not_found`.
    - `verified_quote_integrity`: re-verifying every citation marked ok still passes.
    - The judge runs only for approved cases that have an `expected_point` and an answer of kind `answer`.
    - `BudgetExceeded` stops the run with `stopped`/`remaining` filled; `resume` skips case ids already recorded for `run_id` in `data_dir/reports/eval-<run_id>.json`.
  - `render_eval_report_md(report: EvalReport) -> str`
  - `write_eval_report(pack: Pack, report: EvalReport) -> tuple[Path, Path]` writes `.md` and `.json` under `pack.data_dir/"reports"`

- [ ] **Step 1: Write the failing tests**
  - `test_eval_metrics_on_synthetic`: `retrieval_hit_rate == 1.0`, `not_found_accuracy == 1.0`, `verified_quote_integrity == 1.0`, `passed is True`; q4 appears with status `draft` and isn't counted
  - `test_eval_fails_threshold`: when a scripted answer misses its source, `passed is False`
  - `test_reports_written_with_versions`: the Markdown contains `pack_version(pack)` and the model names, and the JSON round-trips
  - `test_eval_budget_stop_and_resume`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_evaluate.py -q` → FAIL.
- [ ] **Step 3: Implement `evaluate.py`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** (`feat: evaluation runner with judge, thresholds and resumable reports`).

---

### Task 15: Command line and README

**Files:**
- Create: `src/goldthread/cli.py`, `src/goldthread/__main__.py`, `golden-thread/README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above
- Produces: `main(argv: Sequence[str] | None = None) -> int`. Usage: `goldthread --pack PATH [--data-root PATH] <command>`. Commands:
  - `fetch`
  - `ingest`
  - `search QUESTION`: shows the hits only, with no model call
  - `extract [--resume RUN_ID] [--docs DOC_ID ...]`: runs `link_records` afterwards
  - `review-export [--out PATH]`: defaults to `data_dir/review/review-<UTC timestamp>.csv`
  - `review-import PATH --reviewer NAME`
  - `ask QUESTION [--html]`
  - `trace CODE`
  - `check`
  - `test [--resume RUN_ID]`
  - `spend`: the current month and the last run

  Behaviour:
  - Run ids are `YYYYMMDDTHHMMSSZ-<4 hex>`.
  - Every command that calls a model validates the prices first, then prints its result and `render_cost_summary` for the run.
  - An offline pack runs every command inside `no_network()`; `fetch` on an offline pack prints `offline pack: fetch is disabled` to stderr and exits 1.
  - Exit codes: 0 for success; 1 for an error (`PackError`, `OfflineError`, `NetworkBlocked`, a file problem, or a refusal answer); 3 when stopped by the budget (the message names the limit and the resume command).
  - The README covers install, every command with one example, where data lives and why it is git-ignored, and how to set budgets.

- [ ] **Step 1: Write the failing tests**
  - `test_cli_pipeline_offline_under_no_network`: inside `no_network()`, the synthetic pack's `ingest`, `extract`, `review-export`, `ask "What is the fuel temperature limit?"`, `trace "PDC 10"`, `check`, `test` and `spend` each return 0; the review sheet, the reports and the ledger exist under `data_dir`
  - `test_cli_fetch_offline_refused`: exit 1, with stderr containing `offline pack: fetch is disabled`
  - `test_cli_budget_stop_exit_3`: with `extract_pack` monkeypatched to return a report with `stopped="budget: run limit"`, the exit code is 3 and the output contains `--resume`
  - `test_cli_search_no_model_call`: with `get_connector` monkeypatched to raise, `search` still returns 0
  - `test_cli_ask_html`: the output starts with `<`
- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/test_cli.py -q` → FAIL.
- [ ] **Step 3: Implement `cli.py`, `__main__.py` and `README.md`.**
- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest -q` → all pass; `.venv/bin/goldthread --help` lists the 12 commands.
- [ ] **Step 5: Commit** (`feat: goldthread command line and README`).

---

### Task 16: The nrc-xenergy pack (no API spend)

**Files:**
- Create: `golden-thread/packs/nrc-xenergy/` containing `pack.yaml`, `register.csv`, `records.yaml`, `layouts/cfr_section.yaml`, `layouts/regulatory_guide.yaml`, `layouts/topical_report.yaml`, `layouts/nrc_safety_evaluation.yaml`, `layouts/psar_chapter.yaml`, `aliases.csv`, `rules.md`, `answer_format.md`, `outside.md`, `tests.csv`

Pinned content:
- `pack.yaml`:
  - `name: nrc-xenergy`, `sensitivity: public`, `offline: false`, `source_dir: null`
  - models: extract `{claude, claude-opus-5-5, low, 16000}`, answer `{claude, claude-opus-5-5, high, 16000}`, judge `{claude, claude-opus-5-5, low, 4000}`
  - budget `{per_run_usd: 20, per_month_usd: 150}`
  - `withheld_patterns`: set in step 4
- `records.yaml` (record types; the prefix is in brackets):
  - `Requirement` [REQ]: `code`, `text`; required `code`, `text`
  - `AcceptedMethod` [MTH]: `code`, `title`; required `code`
  - `Claim` [CLM]: `key`, `requirement_code`, `text`; required `requirement_code`, `text`
  - `Argument` [ARG]: `key`, `claim_key`, `method_code`, `text`; required `claim_key`, `text`
  - `EvidenceRef` [EVD]: `key`, `argument_key`, `reference`, `title`, `available`; required `argument_key`, `reference`
  - `Finding` [FND]: `key`, `subject_code`, `conclusion`; required `subject_code`, `conclusion`
  - `Condition` [CND]: `key`, `finding_key`, `text`; required `finding_key`, `text`
- Link types:
  - `meets`: Claim.requirement_code → Requirement.code, scope code
  - `supports`: Argument.claim_key → Claim.key, scope chunk
  - `follows`: Argument.method_code → AcceptedMethod.code, scope code
  - `cites`: EvidenceRef.argument_key → Argument.key, scope chunk, reverse
  - `evaluates`: Finding.subject_code → {AcceptedMethod: code, Requirement: code}, scope code
  - `limits`: Condition.finding_key → Finding.key, scope chunk
- Coverage rules:
  - "Requirements with no claim" (Requirement, missing_incoming meets)
  - "Claims with no argument" (Claim, missing_incoming supports)
  - "Arguments citing evidence not loaded" (Argument, has_outgoing cites)
  - "Findings with conditions" (Finding, has_incoming limits)
- `rules.md`: the five rules of spec §7.4, verbatim.
- `answer_format.md`: the trace answer format of spec §7.4, verbatim.

Steps:
- [ ] **Step 1: Make nrc.gov reachable.** Call the environment tool to allow `www.nrc.gov`, `adams.nrc.gov` and `ww2.nrc.gov`, or ask the user to upload the PDFs into `data/nrc-xenergy/cache/` named `<doc_id>@<rev>.pdf`. Check: `curl -sI https://www.nrc.gov/` returns 200, or the files are present.
- [ ] **Step 2: Fill `register.csv`** for the spec §7.4 documents:
  - RG 1.232; RG 1.233; 10 CFR 50.34
  - the X-energy PDC, TRISO-X fuel qualification and core design methods topical reports, each with its NRC final safety evaluation
  - the Long Mott PSAR chapters on design criteria and fuel, with Supplements 1–5
  - the NRC safety evaluation for the Long Mott construction permit
  
  Use ADAMS accession numbers as `doc_id` where they exist, and `10CFR50.34`/`RG1.232`/`RG1.233` otherwise. Revision tokens follow the documents' own labels (`rev3`, `sup1`). Take `status`/`supersedes` only from what each supplement's cover letter states; where it is unclear, register the supplement as issued, record the question in `outside.md`, and tell the user. Check: every URL returns a PDF.
- [ ] **Step 3: Fetch.** `.venv/bin/goldthread --pack packs/nrc-xenergy fetch` → every row lands in `downloaded` or `recorded_checksums`. Commit the register checksums.
- [ ] **Step 4: Ingest and set the withheld markers.** Run `ingest`, then inspect the redacted regions of three documents and set `withheld_patterns` to the markers actually printed. Re-ingest, and check that the report's `flagged` count is above 0 wherever redactions exist and that `skipped` is empty.
- [ ] **Step 5: Write the layouts, aliases and `outside.md`.**
  - Each layout's `example` quotes real ingested text verbatim.
  - Aliases cover the criterion numbering forms (`PDC n`, `MHTGR-DC n`, `Criterion n`), the spec's acronym seed list, and report titles ↔ accession numbers.
  - `outside.md` covers withheld proprietary content, evidence documents, RAIs and audit reports, and drawings.
  
  Check: `.venv/bin/goldthread --pack packs/nrc-xenergy search "PDC 10"` returns hits from the RG and the PSAR.
- [ ] **Step 6: Draft 30 test questions** in `tests.csv`, all `status: draft`, at least 5 with `expect_not_found: yes`. Write them from the ingested passages, using `search` to confirm the expected sources. Check: `load_pack` succeeds and the drafts are listed.
- [ ] **Step 7: Commit the pack configuration** (no data) and ask the user to review the test questions and expected answers. Questions become `approved` only on the user's word.

---

### Task 17: First paid run (gated on the user)

- [ ] **Step 1: Ask the user to confirm** the budget ($20 per run, $150 per month), that their account spending limit is set, and that they want to proceed. Stop if not.
- [ ] **Step 2: Get the API key** through the secure credential form for `api.anthropic.com`. Run the SDK with a placeholder `ANTHROPIC_API_KEY`; the session proxy injects the real key. Check: `.venv/bin/goldthread --pack packs/nrc-xenergy ask "What is RG 1.233 about?"` returns an answer with verified citations and a cost summary.
- [ ] **Step 3: Extract a small subset.** `extract --docs <PDC topical report SE> <RG 1.232>`, then `check`. Report the cost summary and the record counts to the user.
- [ ] **Step 4: Review.** Run `review-export` and send the sheet's location and contents summary to the user for review. Import their decisions with `review-import`.
- [ ] **Step 5: Evaluate.** Once the questions are approved, run `test` and share the evaluation report (metrics, pass/fail, cost) with the user. Nothing under `data/` is committed.
