# Golden Thread

Traceable question-answering over a controlled set of documents. Every statement in an answer carries the document,
revision, page and an exact quote, and every quote is checked word for word against the stored text. Design:
`../docs/superpowers/specs/2026-11-20-golden-thread-design.md`.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

## Packs

A pack is a folder of plain files describing one document set: `pack.yaml` (models per job, budget, offline flag),
`register.csv` (documents, revisions, checksums), `records.yaml` (record types, link types, coverage rules),
`layouts/` (one extraction recipe per document layout), `aliases.csv`, `rules.md`, `answer_format.md`,
`outside.md` and `tests.csv`. A new document set needs a new pack, not code changes. See `packs/nrc-xenergy/`.

## Commands

All commands take `--pack PATH` (and optionally `--data-root PATH`).

| Command | Example | What it does |
|---|---|---|
| `fetch` | `goldthread --pack packs/nrc-xenergy fetch` | Downloads registered documents into the cache and records their checksums. A changed document is quarantined, never used. |
| `ingest` | `goldthread --pack packs/nrc-xenergy ingest` | Reads the documents into the store. Pages with no text layer and withheld text are flagged. |
| `search` | `goldthread --pack packs/nrc-xenergy search "functional containment"` | Shows matching passages. No model call, no cost. |
| `extract` | `goldthread --pack packs/nrc-xenergy extract --docs ML24284A012` | Extracts draft records with the model, then links them. |
| `review-export` | `goldthread --pack packs/nrc-xenergy review-export` | Writes draft records to a spreadsheet for review. |
| `review-import` | `goldthread --pack packs/nrc-xenergy review-import data/nrc-xenergy/review/review-….csv --reviewer "J. Smith"` | Applies the reviewer's decisions (verified, corrected, rejected); quotes are re-checked. |
| `ask` | `goldthread --pack packs/nrc-xenergy ask "How does Long Mott meet design criterion 16?"` | Answers with verified quotes, or "Not found" with the list of documents searched. An answer the model cut short is marked "Incomplete answer", never "Not found". `--html` for HTML. |
| `trace` | `goldthread --pack packs/nrc-xenergy trace "PDC 16"` | Requirement → claim → argument → evidence cited → NRC finding and conditions. |
| `check` | `goldthread --pack packs/nrc-xenergy check` | Coverage rules from the pack, and records citing superseded revisions. |
| `test` | `goldthread --pack packs/nrc-xenergy test` | Runs the pack's approved test questions and writes a report. |
| `spend` | `goldthread --pack packs/nrc-xenergy spend` | Spend for the last run and this month. |

Exit codes: `0` success; `1` error (bad pack, offline violation, file problem, refusal, incomplete answer,
failed evaluation); `3` stopped by the budget (for `extract` and `test` the message gives the `--resume RUN_ID`
command; `ask` makes no model call).

## Where data lives

Everything a pack produces lives under `data/<pack name>/`: downloaded documents (`cache/`), the SQLite store, the
spend ledger, the audit log, review sheets and reports. `data/` sits next to the `packs/` folder (here
`golden-thread/data/`), whatever folder you run the command from; `$GT_DATA_DIR` or `--data-root` puts it elsewhere.
The folder is git-ignored on purpose: it holds copies of document text and must never be committed, and for a
sensitive pack it is as sensitive as the most sensitive document in it. An offline pack's documents go in
`packs/<name>/source/`, which is git-ignored too. Every command warns if its data or source folder is inside a git
repository and not ignored.

`fetch` saves only files that start like a PDF (`%PDF-`) and never records the checksum of anything else. A cached
file that does not match its register checksum is replaced only by a download that does, and is then kept in
`cache/quarantine/` under a name that includes its checksum; it is never deleted or overwritten.

## Review sheets

`review-export` writes one row per draft record. Columns:

| Column | Meaning |
|---|---|
| `id`, `type`, `status`, `address` | The record. Do not edit. |
| `quote`, `fields_json` | What the model extracted. Edits here count as corrections. |
| `quote_check` | Whether the quote is found word for word at the address now. |
| `decision` | `verified`, `corrected` or `rejected`. Rows left blank are not changed. |
| `corrected_fields_json` | Field values to change, as JSON, e.g. `{"requirement_code": "PDC 11"}`. Applied on top of `fields_json`. |
| `corrected_quote` | A replacement quote. |
| `note` | For the reviewer; not imported. |

`review-import` re-checks every quote, refuses a row marked `verified` whose `quote` or `fields_json` was edited (use
`corrected`), refuses unknown field names and invalid JSON, and leaves a record as draft if a required field is empty.
The sheet must be saved as UTF-8 ("CSV UTF-8" in Excel); otherwise nothing is applied. After an import the links
between records are recomputed, so `trace` and `check` reflect the decisions at once.

## Budgets

`pack.yaml` sets `budget: {per_run_usd, per_month_usd}`. Before every paid model call the engine works out the worst
case (input tokens plus the maximum output, at the model's price in `src/goldthread/prices.yaml`) and stops cleanly
if the run or month limit would be exceeded. Actual costs are recorded in the ledger. A stopped run lists what it did
not process and resumes with `--resume RUN_ID`. Keep a spending limit on the Anthropic account as the outer safety
net, and update `prices.yaml` when prices change.

## Offline packs

`offline: true` in `pack.yaml` means: hosted providers are refused, `fetch` is disabled, documents are read from
`source_dir`, and every command runs with outbound network blocked. A `sensitive` pack must be offline.
