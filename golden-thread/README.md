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
| `ask` | `goldthread --pack packs/nrc-xenergy ask "How does Long Mott meet design criterion 16?"` | Answers with verified quotes, or "Not found" with the list of documents searched. `--html` for HTML. |
| `trace` | `goldthread --pack packs/nrc-xenergy trace "PDC 16"` | Requirement → claim → argument → evidence cited → NRC finding and conditions. |
| `check` | `goldthread --pack packs/nrc-xenergy check` | Coverage rules from the pack, and records citing superseded revisions. |
| `test` | `goldthread --pack packs/nrc-xenergy test` | Runs the pack's approved test questions and writes a report. |
| `spend` | `goldthread --pack packs/nrc-xenergy spend` | Spend for the last run and this month. |

Exit codes: `0` success; `1` error (bad pack, offline violation, file problem, refusal, failed evaluation);
`3` stopped by the budget (the message gives the `--resume RUN_ID` command).

## Where data lives

Everything a pack produces lives under `data/<pack name>/` (or `$GT_DATA_DIR`): downloaded documents (`cache/`), the
SQLite store, the spend ledger, the audit log, review sheets and reports. The folder is git-ignored on purpose: it
holds copies of document text and must never be committed, and for a sensitive pack it is as sensitive as the most
sensitive document in it.

## Budgets

`pack.yaml` sets `budget: {per_run_usd, per_month_usd}`. Before every paid model call the engine works out the worst
case (input tokens plus the maximum output, at the model's price in `src/goldthread/prices.yaml`) and stops cleanly
if the run or month limit would be exceeded. Actual costs are recorded in the ledger. A stopped run lists what it did
not process and resumes with `--resume RUN_ID`. Keep a spending limit on the Anthropic account as the outer safety
net, and update `prices.yaml` when prices change.

## Offline packs

`offline: true` in `pack.yaml` means: hosted providers are refused, `fetch` is disabled, documents are read from
`source_dir`, and every command runs with outbound network blocked. A `sensitive` pack must be offline.
