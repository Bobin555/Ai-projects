# Golden Thread: traceable question-answering over controlled documents

Design · 2026-11-20 · Status: draft for review

## 1. Intent

**What.** A question-answering engine for document sets where every detail matters. It answers only from the documents, quotes them exactly, checks every quote against the source automatically, and builds a traceable structure from requirements down to evidence. Each document set is a *pack* of plain configuration files; the engine itself does not change between packs.

**Who.** A safety case and licensing engineer. First on public US NRC documents for X-energy's Xe-100 (Long Mott Generating Station). Later, inside the engineer's own organisation's network, on sensitive safety case and GDA documents with a locally hosted model.

**Why.**
- In safety cases a confident wrong answer is the dangerous failure. General chat tools and typical RAG paraphrase, blend sources and cannot prove where an answer came from.
- Tracing a requirement through claims, arguments, evidence and regulator findings across thousands of pages (the "golden thread") is slow manual work.
- Sensitive documents may not leave the organisation's network, so the engine must also work fully offline.

**Where the principles came from.** A small worked example (checking product labels against reference sheets) established the rules this design carries over:

| Lesson from the worked example | Rule in this design |
|---|---|
| Every row named its source sheet, code and date | Every statement carries document, revision, location and an exact quote |
| A fixed table beat summaries | Extraction fills fixed record types, never free-form summaries |
| "Other names" was the most important column | Each pack has an alias table used in search |
| "From the documents" was kept apart from "added by me" | Records stay `draft` until a person verifies them; provenance is always shown |
| Unclear text was flagged instead of guessed | Unreadable, cut-off or withheld text is flagged, never silently repaired |
| "None found" is not "safe" | "Not found" always states what was searched |
| The newer label beat the older list | The newest issued revision wins; older ones are flagged when used |
| One item appeared on two lists | Records are linked as a graph and traceable both ways |
| Some sources had no label at all | Each pack states what is outside its corpus |
| Two sheet layouts needed two recipes | One extraction recipe per document layout |

## 2. Goals

- **G1 Exact, verified quotes.** Every factual statement in an answer cites document ID, revision, page (and section where known) and an exact quote. A deterministic checker confirms each quote appears in the cited passage of the cited revision. Statements whose quotes fail are flagged ⚠ and never shown as verified.
- **G2 Honest "not found".** When the documents don't support an answer, say so and list the documents and revisions searched.
- **G3 Traceable records.** Extract requirements, claims, arguments, evidence references, regulator findings and conditions into fixed records with source addresses and quotes, linked to each other.
- **G4 Revisions.** Track revisions and supplements; use the newest issued one by default; flag superseded content when it is cited.
- **G5 Packs.** A new document set needs only a new pack (configuration files and test questions), with no engine code changes.
- **G6 Offline mode.** A pack marked `offline` runs with no outbound network: local model, local search, no telemetry.
- **G7 Measured.** Each pack has a test set; the engine reports search, quote and "not found" scores per run, stored with the model and pack version.

## 3. Non-goals (v1)

- Evidence documents (calculations, test reports). The evidence layer holds *references* only, as cited in the documents, marked not available.
- Judging whether a safety argument is adequate. The engine finds, quotes and traces; engineers judge.
- A web interface. v1 is a command-line tool that writes Markdown and HTML reports.
- A multi-user service, logins and per-document access control. Packs are kept separate; finer access control is a later step.
- Fine-tuning any model.
- Drawings, CAD files, spreadsheets.
- UK GDA documents and sensitive documents (later packs; sensitive ones are never put in this repository or a cloud session).

## 4. Anti-goals (a failure even if everything else works)

- A quote displayed as verified that is not exactly in the source.
- "Not found" presented as "compliant", "safe" or "no issue".
- Mixing content from different packs, or from different revisions, without saying so.
- Silently correcting source text (typos, truncation, redactions).
- Any network call from a pack marked `offline`.
- Source documents, extracted text, indexes, logs, or sensitive or personal data committed to the repository.

## 5. Constraints

- **Sensitive documents never leave the user's network.** The engine must run fully offline: a local model (Ollama, or an OpenAI-compatible local server such as vLLM), a local embedding model, local storage, no telemetry, and dependencies installable without internet access.
- **This cloud session** has no GPU, and its network policy currently blocks nrc.gov. Access will be requested when building starts; alternatively the user uploads the public PDFs.
- **Public NRC documents are redacted.** Proprietary content is withheld, so most evidence is unavailable.
- **Repository** (`bobin555/ai-projects`): code, pack configuration, tests and docs only. Documents are downloaded into a git-ignored cache.
- **Language:** Python, with few dependencies, so it can be carried into a restricted network.
- **In-network hardware is unknown.** Model size will be chosen from test results.

## 6. Approaches considered

### 6.1 How the model gets the knowledge
- **RAG (chosen).** Shows sources, quotes exactly, handles new revisions by re-indexing, supports access control and "not found", and can be checked automatically.
- **Fine-tuning (rejected as the knowledge store).** Cannot show sources, blends facts, keeps superseded content, and exposes everything it was trained on to anyone who can query it. May be used later only to improve search or for narrow extraction tasks.

### 6.2 Where it runs
- **A. One fully internal system for sensitive documents (chosen for in-network use).** No routing rules and no risk of sending sensitive text out.
- **B. Split: sensitive documents local, non-sensitive ones on a hosted model.** Only if test results show local quality is insufficient; needs reliable sensitivity labels.
- **Sending "relevant passages" of sensitive documents to a hosted model:** rejected, because the passages are the sensitive part.
- For the **public** pack a hosted model is allowed; see open question Q1.

### 6.3 Replicating to new document sets
- **A. Engine plus packs (chosen).** Engine fixes help every pack, packs stay separate, and pack changes are small files that can be reviewed in git.
- **B. Copy the whole system per document set.** Copies drift, fixes don't propagate, and each copy needs its own assurance.
- **C. One shared index.** Mixes sensitivity levels and projects, blends sources, and makes access control hard.

### 6.4 Where regulatory documents sit
- **Regulations are requirements and accepted methods (chosen).** Regulations and design criteria state what must be shown. Regulatory Guides and approved topical reports are accepted methods an argument may cite. Arguments come from the applicant's documents; regulator evaluations are findings.
- **Regulations as arguments (rejected).** A regulation says what must be shown, not how this design shows it.

## 7. Design

### 7.1 Overview

```
pack register ──► fetch (cache, checksums) ──► read (pages, headings, paragraphs, tables)
                                                    │
                                                    ▼
                                      passage store (one per pack)
                                 keyword index + optional vector index
                                                    │
              ┌─────────────────────────────────────┼──────────────────────────────┐
              ▼                                     ▼                              ▼
       extract records                     ask (search → model)             checks and tests
   (draft → human verified)          answer with addresses + quotes    coverage, revisions,
              │                                     │                    test-set scores
              └──────────────► quote verifier ◄─────┘
                                     │
                                     ▼
                       reports (Markdown/HTML) + audit log
```

### 7.2 Engine components

1. **Register and fetch.** The pack's `register.csv` lists each document: `doc_id` (the NRC ADAMS accession number for NRC documents), title, layout, revision or supplement, date, status (`issued` or `superseded`), `supersedes`, source URL and SHA-256 checksum. `fetch` downloads into `cache/<pack>/` (git-ignored), records the checksum on first download and verifies it afterwards. Offline packs never fetch; they read from a local folder.
2. **Reader.** Converts each PDF into passages with page number, heading path, paragraph text and tables. Text is stored exactly as extracted; normalisation is used only for matching. Every passage has a stable address, `doc_id@rev#p<page>.<n>`. Pages with no text layer are flagged ⚠ (OCR is a later option). Withheld or redacted regions are recorded as `[withheld]`, never guessed. The v1 reader is pdfplumber (MIT licence, pure Python, no model downloads). PyMuPDF is faster but AGPL-licensed, which many organisations restrict. A layout-aware reader (for example Docling) can be added behind the same interface.
3. **Store.** One store per pack. v1 uses SQLite with FTS5 keyword search and an optional vector table, behind an interface so PostgreSQL with pgvector can replace it inside the user's network.
4. **Aliases.** `aliases.csv` maps alternative names to a canonical term (for example "Criterion 10", "MHTGR-DC 10" and "PDC 10"). Queries are expanded with aliases. Identifiers (criterion numbers, CFR sections, Regulatory Guide numbers, accession numbers) must match exactly.
5. **Search.** Keyword search with aliases in v1; embedding search is added when a local embedding model is available, and results are merged. Default filter: current revisions only. Returns passages with their addresses.
6. **Model adapter.** One interface with two back-ends, selected by the pack:
   - *Hosted:* the Claude API with model `claude-opus-5-5`. Answers use the API's citations feature: retrieved passages are passed as one custom-content document per source document, one content block per passage, so each citation maps back to a passage address. Extraction uses structured output. These are separate calls, because the API does not allow citations and structured output in the same request. Bulk extraction may use the Batch API.
   - *Local:* Ollama or an OpenAI-compatible local server, with JSON-schema-constrained output that requires a passage ID and an exact quote for every statement.
   - A pack marked `offline` cannot select the hosted back-end; the engine refuses at start-up.
7. **Answerer.** Question → aliases → search → model → answer laid out as the pack's `answer_format.md` specifies: each statement with its address and quote, or "Not found. Searched: …".
8. **Quote verifier.** Deterministic, no model involved. A quote passes only if it appears in the cited passage of the cited revision after normalising whitespace, line-break hyphenation and quotation marks. It also checks that the cited revision is current. Failures are flagged ⚠ on the statement; nothing is silently dropped or marked verified.
9. **Extractor.** Each document layout has a recipe in `layouts/<layout>.yaml` naming the record types to look for, instructions for each field and a worked example. Extraction runs section by section, with the heading path as context. The model fills records with source addresses and quotes; every record starts as `draft`, and the verifier checks its quotes. A person reviews records in an exported review sheet (CSV) and marks each `verified`, `corrected` or `rejected`; the import records who reviewed it and when.
10. **Records and links.** Record types and fields come from `records.yaml`. Links are typed (for example `meets`, `supports`, `follows`, `cites`, `evaluates`, `limits`). Exports: CSV and Markdown tables, and a trace report per requirement.
11. **Checks.** Coverage (requirements with no claim, claims with no argument, arguments citing evidence that is not loaded, findings with conditions) and revision drift (citations of superseded revisions). Value-consistency checks come later.
12. **Test runner.** Runs `tests.csv`: question, expected source(s), expected key point, or expected "not found". Scores: expected source in the top 10 results; share of displayed quotes that pass verification; expected source cited; "not found" given for out-of-corpus questions. Writes a report and stores the results with the model, back-end and pack version.
13. **Audit log.** One JSON line per question: time, pack version, question, passages retrieved, model and back-end, answer and verifier results. Stored with the pack's data and git-ignored.
14. **Command line.** `fetch`, `ingest`, `extract`, `review-export`, `review-import`, `ask`, `trace`, `check`, `test`.

### 7.3 Pack format

```
packs/<name>/
  pack.yaml          name, description, sensitivity (public or sensitive), offline (true or false),
                     model back-end and model, embedding model (optional)
  register.csv       documents, revisions, status, URLs, checksums
  records.yaml       record types, fields, link types
  layouts/           one extraction recipe per document layout
  aliases.csv        alternative names → canonical term
  rules.md           rules applied by the answerer and the checks
  answer_format.md   how answers are laid out
  outside.md         what is known to be outside this corpus
  tests.csv          test questions with expected sources or "not found"
```

A second, tiny pack built from synthetic documents lives in the engine's own tests, to prove that a new pack needs no code changes.

### 7.4 First pack: `nrc-xenergy` (public)

**Purpose.** Trace a requirement through Long Mott's claim, the argument, the evidence cited and the NRC's finding.

**Initial documents.** Accession numbers are confirmed from NRC pages at build time. Start small and grow after the first test run.
- NRC Regulatory Guide 1.232 (design criteria for non-light-water reactors, including the modular HTGR criteria) and Regulatory Guide 1.233 (risk-informed method for the licensing basis).
- 10 CFR 50.34(a) (contents of a construction permit application).
- X-energy topical reports with the NRC's final safety evaluations: Principal Design Criteria (evaluation October 2024), TRISO-X Pebble Fuel Qualification Methodology (March 2023) and Core Design Methods and Analysis (August 2025).
- The Long Mott Generating Station construction permit application: the PSAR chapters that address the principal design criteria and fuel, with Supplements 1–5 (October–December 2025) registered as revisions.
- The NRC's safety evaluation for the Long Mott construction permit (permit issued 9 November 2026).

**Record types.**

| Record | Meaning | Typical source |
|---|---|---|
| Requirement | What must be shown | CFR, design criteria (RG 1.232), the applicant's adopted principal design criteria |
| AcceptedMethod | A method the regulator has accepted | Regulatory Guides, approved topical reports |
| Claim | "The design meets requirement X" | PSAR |
| Argument | How the design meets it, including methods followed | PSAR, topical reports |
| EvidenceRef | Evidence the argument cites (report number, title), marked `available: no` | PSAR, topical reports |
| Finding | The NRC's conclusion on a claim, argument or report | NRC safety evaluations |
| Condition | A limitation or condition attached to a finding | NRC safety evaluations |

Links: Claim `meets` Requirement · Argument `supports` Claim · Argument `follows` AcceptedMethod · Argument `cites` EvidenceRef · Finding `evaluates` Claim, Argument or report · Condition `limits` Finding.

**Layouts:** CFR section, Regulatory Guide, topical report, NRC safety evaluation, PSAR chapter.

**Aliases (seed):** criterion numbering forms; acronyms such as PSAR, SE, TR, RAI, RG, PDC, MHTGR-DC, TRISO, LBE, AOO, DBE, BDBE, DBA, SR, NSRST and LMP; report titles ↔ accession numbers; plant and system names.

**Rules.**
- The newest issued revision or supplement wins; older ones are flagged when cited.
- A Finding is always shown with its Conditions.
- `[withheld]` text is reported as withheld, never inferred.
- EvidenceRefs are shown as "cited, not available in this pack".
- "Not found" lists the documents and revisions searched.

**Answer format (trace).** Requirement → Claim (where) → Argument (key quotes) → Evidence cited (not available) → NRC finding and conditions. Every line carries document, revision, page and an exact quote.

**Tests.** 30 questions to start, including at least 5 whose answers are not in the corpus. Claude drafts candidate questions from the documents; the user corrects the expected answers and sources, since that judgement is theirs.

### 7.5 Offline profile (for in-network use)

- `offline: true` in `pack.yaml` means the hosted back-end is refused, `fetch` is disabled, Hugging Face libraries are forced offline and telemetry is off.
- Local model through Ollama (trial) or vLLM (team service); local embedding model.
- Dependencies shipped as a wheelhouse; model files moved through the organisation's approved transfer process and verified by checksum.
- Outbound traffic blocked at the server. The store, cache and logs are treated as being as sensitive as the most sensitive document in the pack.

### 7.6 What goes in the repository

Code, pack configuration (registers with accession numbers, URLs and checksums), layouts, aliases, rules, tests and docs. Never: downloaded documents, extracted text, stores, logs, review sheets containing document text, or sensitive or personal material.

## 8. Success criteria (v1)

- 100% of quotes displayed as verified pass the verifier (a hard rule, not a target).
- Expected source in the top 10 search results for at least 80% of test questions (an initial target, revisited after the first run).
- Every out-of-corpus test question is answered "not found".
- The synthetic second pack runs with no engine changes.
- An `offline` pack completes its tests with outbound network blocked.

## 9. Decided with the user

- RAG, not fine-tuning, as the knowledge source.
- Sensitive documents stay in the user's network with a local model, and are never shared in a cloud chat.
- Engine plus packs.
- First pack: public NRC documents for X-energy and Long Mott.
- Regulations as requirements and accepted methods; applicant documents as claims and arguments; NRC evaluations as findings; evidence as references only, for now.
- First job: trace a requirement through claim, argument, cited evidence and NRC finding.

## 10. Calls made by Claude (open to change)

- Python; SQLite (FTS5) for v1, with a path to PostgreSQL and pgvector.
- Keyword search with aliases first; embedding search added behind the same interface.
- pdfplumber reader first (permissive licence, carries into a restricted network); a layout-aware reader later.
- Command line with Markdown and HTML reports; no web interface in v1.
- Human review through exported review sheets.
- 30 test questions to start; Claude drafts, the user decides the expected answers.
- Initial document scope as listed in 7.4, growing after the first test run.
- Documents kept out of git, in a cache folder.
- Success-criteria thresholds in section 8.

## 11. Open questions

- **Q1 (the user's decision): which model reads and answers for the public pack while we build?** Hosted (Claude API: best quality now, needs an API key and has a per-use cost), local (Ollama on the user's own computer: matches the future in-network setup, no per-use cost, lower quality), or both. Pending.

## 12. Later

- UK GDA public pack: ONR's Safety Assessment Principles as requirements, PCSR chapters as claims and arguments, ONR assessment reports as findings.
- Sensitive packs inside the user's network.
- Evidence layer, once evidence documents are available.
- Value-consistency checks, a web interface and per-document access control.
