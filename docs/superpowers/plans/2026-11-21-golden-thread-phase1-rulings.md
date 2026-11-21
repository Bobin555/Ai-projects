# Golden Thread phase 1 — fixes, rulings and findings

Companion to `2026-11-21-golden-thread-phase1.md`. Written 2026-11-21 after the final review's fix pass and Task 16.

## Final review

A fresh reviewer (a separate Claude Opus agent; Fable 5.2 was unavailable without usage credits) reviewed the whole branch
and returned **"with fixes"**: 2 Critical, 12 Important and 11 Minor findings. Every Critical and Important finding was
fixed in one pass, each with a test written first and seen to fail, plus Minors M1–M5 and M9, part of M7, and M10
(re-graded to Important). The suite went from 145 to 201 passing tests.

| Finding | What a user would have got | Fix |
|---|---|---|
| C1, I7 | Rejected or corrected records kept their old links in traces and coverage checks | Links are recomputed from the records after every extract and review import |
| C2 | A trace showed a reviewed quote as fine even after its document was superseded | The trace re-checks every quote when it is shown |
| I1 | "PDC 1" matched "PDC 10"; "RG 1.23" matched "RG 1.232"; "release" was cut to "relea" | Whole-token matching; only numbered terms filter results |
| I2, I11, I12 | Lines starting with a number were lost as false headings; redactions split across lines or in tables went unflagged | Stricter heading rule, page-wide redaction matching, scanned-page detection, heading paths in prompts |
| I3, M3 | An answer cut off by the token limit was reported as "Not found"; short unsourced sentences showed without a warning | New "Incomplete answer" result; short factual sentences flagged |
| I4 | A server-side fallback could cost more than the budget check allowed for | Every attempt priced; the pre-check reserves for a fallback |
| I5 | Fetch could save an HTML page as a PDF and later overwrite the user's own copy | Only real PDFs are saved; replaced files are kept in quarantine |
| I6 | Two records quoting the same sentence collapsed into one | Record ids include identity fields |
| I8, M10 | A trace's "Not found" listed documents that were never (fully) extracted; failed chunks counted as done | Traces list what was searched and what was not; failed chunks are retried with --resume |
| I9, M7 part | Edits typed into the review sheet's quote or fields cells were silently ignored | Applied under "corrected", refused under "verified"; required fields re-checked; non-UTF-8 sheets change nothing |
| I10 | Data could be written outside the git-ignored folder | Data sits beside the packs folder; a warning if it would be committed |
| M1, M2, M4, M5, M9 | Budget stop traceback in ask; DNS and UDP not blocked offline; thin audit line; evaluation gaps; traces wandering into other requirements | All fixed with tests |

## Rulings I made

Every decision taken without asking, in the order made (61 in all), each with what it costs if it is wrong.

1. **Setup.** no new worktree; work on the existing session branch claude/eager-bohr-kzil96 (not main) — the session requires all work on this branch — if wrong: none, branch is already isolated.
2. **Setup.** Task 17 (paid API run) is gated on the user per plan; final review runs after Task 16 and Task 17 waits for the user's yes — cost if wrong: one extra message.
3. **Pre-flight (Tasks 8 and 14).** T8 FakeConnector judge parsing ↔ T14 judge user text "QUESTION: …\nEXPECTED: …\nANSWER: …": T8 says "the line after EXPECTED:" but T14/T8 tests put the value on the same line. Ruling: parse text after "EXPECTED:" to end of that line, and text after "ANSWER:" to end of text — matches both tests — cost if wrong: fake judge only.
4. **Task 2.** heading lines end the current passage and update the heading path but are not emitted as passages (their text is carried in Passage.heading) — avoids duplicate heading-only passages; headings stay searchable via the FTS heading column — cost if wrong: a quote of a bare heading line won't verify.
5. **Task 3.** test_fts_search_excludes_superseded uses the phrase '"fuel temperature limit"' instead of '"temperature"' — the SE fixture also contains 'temperature', so 'only SYN-SAR@r2' could not hold; the phrase keeps the test's intent (superseded r1 excluded unless asked) — cost if wrong: none.
6. **Task 4.** FetchReport gains failed: list[str] ('<key>: no url in register' / 'download failed: ...') and a failed download no longer aborts the whole fetch — the brief had no place to report these; additive field — cost if wrong: none (callers ignore it).
7. **Task 5.** alias word boundaries use (?<![a-z0-9])/(?![a-z0-9]) lookarounds instead of \b — variants such as '50.34(a)' end in a non-word character, where \b would never match — cost if wrong: none.
8. **Task 7.** 'max of the requested and serving models' prices' is taken component-wise (input, output, cache read, cache write each at the higher rate), and fallback is also set whenever served_by differs from the requested model — conservative for a guard; the test for an unknown serving model needs the auto-flag — cost if wrong: slight over-counting of spend.
9. **Task 7.** per_job_model in the cost summary is keyed by the serving model, not the requested one — shows which model actually ran — cost if wrong: none.
10. **Task 8.** FakeConnector takes script/extractions as Optional (default None → empty dict) rather than literal {} defaults — avoids shared mutable defaults; same call shape — cost if wrong: none.
11. **Task 9.** an empty model reply (no text) is treated like NOT_FOUND (kind not_found, with the searched list) rather than an empty 'answer' — an empty answer would look like a result with nothing in it — cost if wrong: an empty reply is reported as not found instead of as an error.
12. **Task 10.** structured() reports unparseable JSON as data {} with stop_reason kept ('max_tokens') or set to 'invalid_json', instead of raising — the extractor can then flag the chunk instead of crashing the run — cost if wrong: a bad response becomes an empty extraction that must be noticed in the report.
13. **Task 11.** ExtractReport gains failed_chunks ("<chunk>: <stop reason>") for refusals, truncation or invalid JSON; such chunks are still marked done so a resume doesn't pay for them again — they must be visible in the report — cost if wrong: a failed chunk needs a fresh run id to retry.
14. **Task 11.** the linker ignores rejected records as both sources and targets — a rejected record must not appear in traces — cost if wrong: none.
15. **Task 11.** the extraction item's top-level key is copied into fields['key'] when the record type has a key field — chunk-scope links match on fields — cost if wrong: none.
16. **Task 12.** a 'verified' decision also re-verifies the quote; if it fails, the record stays draft with a quote_failed flag and is listed in reverified_failed — the spec's hard rule says nothing shown as verified may fail the verifier — cost if wrong: a reviewer must correct the quote before the record can be verified.
17. **Task 13.** trace and checks skip rejected records, and the trace also shows each record's flags (e.g. ⚠ quote_failed) — a trace must not hide a failed quote — cost if wrong: none.
18. **Task 14.** run_eval saves the JSON report after every question (not only at the end) so --resume works after a budget stop; CaseResult gains integrity_failures and the metrics add expected_source_cited_rate and judge_yes_rate for information (not thresholds) — cost if wrong: none.
19. **Task 14.** a run with no approved questions has empty metrics and passed=False — passing must mean something was checked — cost if wrong: none.
20. **Task 15.** the CLI has the 11 commands the brief names; its "12 commands" was a counting slip — cost if wrong: none.
21. **Task 15.** 'test' exits 1 when the evaluation fails its thresholds (0 only when it passes); cost summaries and budget-stop messages go to stderr so stdout stays clean for answers and HTML — cost if wrong: scripts that expected exit 0 on a failed evaluation.
22. **Task 15.** Ledger gains last_run_id() for the spend command; resume hints use the report's run_id — cost if wrong: none.
23. **Task 16.** the engine keeps its honest User-Agent and does not imitate a browser to get past nrc.gov's filter — circumventing a site's access control is not ours to decide — cost if wrong: the user downloads ~10 PDFs by hand.
24. **Task 16.** register built from NRC's own pages: RG 1.232 ML17325A611, RG 1.233 ML20091L698, PDC TR rev3 ML24047A308 + final SE ML24284A012, TRISO-X TR ML21246A289 + feedback ML22327A199, core design TR rev2 ML25071A399 + final SE ML25094A140, Long Mott final SE ML26295A004; Long Mott PSAR chapters (CPA Revision 1, package ML26261A419) not registered until downloaded; nothing marked superseded until the cover letters are read — cost if wrong: a register row needs correcting.
25. **Task 16.** layout examples describe structure without quoting NRC text, to be replaced with real quotes after ingest — no invented regulatory text — cost if wrong: weaker extraction until replaced.
26. **Setup.** final review runs now (engine complete; Task 16 data steps and Task 17 wait on the user) — cost if wrong: config-only changes after the review are not reviewed.
27. **Task 16.** the register uses document accession numbers inside each ADAMS package (ML24047A310, ML22327A201, ML25071A402, ML26295A007) instead of the package numbers, leaves cover letters and affidavits out, registers TRISO-X TR as rev2 (its cover letter says Revision 2) and loads 10 CFR as the whole of Part 50 (user-supplied eCFR PDF) — cost if wrong: a register row needs correcting.
28. **Final review.** M9 rule is "a node reached by an outgoing link does not go back in through that same link type", not "never expand incoming links" — keeps SE findings on a shared method or requirement in the thread while cutting the method's other users — cost if wrong: a leak path through a different link type in a future schema
29. **Final review.** I8 counts a document as searched only when every chunk was extracted in some run; partly extracted documents are listed under "Not yet extracted" with n/m chunks — a partial extraction listed as searched would make "not found" look complete — cost if wrong: chunk ids drift if the reader changes after extraction, so a re-ingested document can look extracted until re-extracted
30. **Final review.** record identity values are normalised with normalise_term (case, hyphens, spaces) before hashing — "PDC 10" and "pdc-10" from two runs stay one record — cost if wrong: alias spellings ("PDC 10" vs "Criterion 10") of one claim still make two records; review shows both
31. **Final review.** only alias groups containing a digit (and exact identifiers) filter search results; acronym groups (SE, PDC, RG) only widen the keyword query — an acronym filter let "PDC 16" through for a "PDC 10" question — cost if wrong: a question naming only an acronym ("what does the SE say") is no longer narrowed to passages that use it
32. **Final review.** Task 9's ruling "an empty reply is not found" is overturned — an empty reply (any stop reason but refusal) is "incomplete", and NOT_FOUND counts only when the reply finished (end_turn or stop_sequence) — a reply cut off by max_tokens must never read as "the documents do not say" — cost if wrong: a model that answers NOT_FOUND and hits max_tokens at the same moment shows as incomplete and the user asks again
33. **Final review.** with per-attempt usage present, the ledger's token columns are the sum of attempts and each attempt is priced at its own model (unknown model: most expensive, flagged); the pre-check with fallback on reserves the requested model's worst case plus the most expensive model's — exact bill instead of the earlier max(requested, served) guess — cost if wrong: the pre-check stops a run up to one extra worst-case call earlier than strictly needed
34. **Final review.** quotes_verified_rate is reported but has no pass threshold — the spec's thresholds are retrieval, not-found accuracy and verified-quote integrity; a flagged quote is already shown to the reader — cost if wrong: an evaluation with many failed quotes still passes if the three thresholded metrics pass
35. **Final review.** a cached file that is not a PDF, or does not match its register checksum, is replaced only by a download that is a PDF matching the register; it is then moved to cache/quarantine/<key>.<sha12>.pdf, otherwise left in place and reported — the cache never ends up worse than before and nothing is overwritten — cost if wrong: a stale cached file stays in place until a good download exists, so ingest keeps skipping it with "checksum mismatch"
36. **Final review.** a cached non-PDF that matches a pinned register checksum is reported ("the register checksum is wrong") and neither moved nor re-downloaded; fetch never edits a pinned checksum — the register is reviewed, committed evidence — cost if wrong: the user has to clear the checksum by hand
37. **Final review.** review import refuses unknown field names in fields_json and corrected_fields_json — a misspelt name otherwise left the old value in place under "corrected", the same silent loss as I9 — cost if wrong: a pack whose records.yaml lacks a field the reviewer needs must be updated before that correction can be imported
38. **Final review.** the default data root is <project>/data when the pack sits in <project>/packs/<name> (else ./data); the CLI warns, but does not stop, when a data or source folder is inside a git repository and not ignored — a stop would block legitimate setups with their own ignore rules — cost if wrong: a user who ignores the warning can still commit document text
39. **Final review.** no_network also blocks gethostbyaddr, getnameinfo and sendmsg, beyond the review's list — the same class of hole as gethostbyname and sendto — cost if wrong: none known; offline packs make no legitimate lookups
40. **Final review.** M10 re-graded from Minor to Important — with I8's extraction status, a failed chunk made its document count as searched, so a trace's "Not found" could cover text the model never read — cost if wrong: one extra fix in the pass, no behaviour risk
41. **Final review.** Task 11's ruling "failed chunks are marked done" is overturned — a chunk is done only when its reply finished (end_turn); extract exits 1 and prints the --resume command — cost if wrong: a chunk that always fails (a refusal) is retried and paid for on each resume until the user leaves that document out
42. **Final review.** the review's corrections to the Task 2, 5, 7 and 13 rulings are accepted — fixed by I2/I11 (headings), I1 (boundaries in the search filter), I4 (fallback in the pre-check) and C1/C2 (rejected links, stale flags) — cost if wrong: none; each has a regression test
43. **Final review.** declined 1 (Task 16 PDFs, Task 17) — stands: the user uploaded the PDFs and Task 16 resumes now; Task 17 waits for the user's yes — cost if wrong: none
44. **Final review.** declined 2 (aliases merge MHTGR-DC n and X-energy PDC n) — stands, as in the spec's example; raised with the user as a pack decision — cost if wrong: a "PDC 16" trace shows the NRC's MHTGR-DC 16 and X-energy's PDC 16 together; each carries its own source text, so a wording difference stays visible
45. **Final review.** declined 3 (Microsoft Foundry rejects server-side fallbacks) — stands for phase 1; the phase 2 connector must set fallback = False and send no fallbacks — cost if wrong: phase 2's first call fails, caught by its tests
46. **Final review.** declined 4 (not_found_accuracy fails in-corpus questions answered "not found") — stands: missing an answer the corpus holds is a real failure for a safety case — cost if wrong: evaluations fail more often than spec §8's wording requires; the report names each question
47. **Final review.** declined 5 (black-box redactions with no text marker) — stands as a stated limit — cost if wrong: an answer can miss text hidden under an unmarked black box, with no withheld flag
48. **Final review.** declined 6 (multi-column layouts) — stands (spec defers a layout-aware reader); Task 16 inspects NRC passages for interleaved columns — cost if wrong: interleaved text reads oddly and its quotes fail verification, which is flagged
49. **Final review.** declined 7 (embeddings, Batch API, OCR, record exports, trace report files) — stand outside this plan, in the spec's Later — cost if wrong: none now
50. **Final review.** declined 8 (concurrent processes racing on one ledger) — stands for a single-user CLI; README now says one paid command at a time per pack — cost if wrong: two concurrent paid runs can overshoot a limit by about one worst-case call each; the account limit still holds
51. **Final review.** declined 9 (spend logged only after a successful response) — stands: failed requests are rarely billed and the account limit is the outer net — cost if wrong: a few failed calls' costs are missing from the ledger
52. **Final review.** declined 10 (NFKC folding in the verifier) — stands, pinned by the plan — cost if wrong: a quote differing from its source only in superscripts or ligatures verifies
53. **Final review.** declined 11 (Hugging Face offline settings) — stands: no Hugging Face dependency in phase 1; phase 2's local connector must set HF_HUB_OFFLINE — cost if wrong: none in phase 1
54. **Final review.** declined 12 (identifier passages pushed out of the 50-candidate pool) — stands pending Task 16: every NRC test question is checked with goldthread search, and a miss becomes a finding — cost if wrong: an identifier question answers "not found" although the passage exists
55. **Final review.** declined 13 (Excel semicolon CSV in other locales) — stands: such a sheet fails loudly (missing columns) and nothing is applied — cost if wrong: a reviewer in a comma-decimal locale must change Excel's list separator
56. **Final review.** declined 14 (uncommitted register edits outside the reviewed range) — committed in dae768e after the review; Task 16 re-checks each register row against its PDF — cost if wrong: those rows were not seen by the fresh reviewer
57. **Task 16.** withheld_patterns are '\[\[.*?\]\]P?' (a whole redaction on a page, across passages), '\[\[' (an opening with no closing: OCR'd table cells, redactions crossing a page break) and '\]\]P' (a closing carried over from the previous page); a bare ']]' is left out because it also ends citations such as "[23]]" — re-ingest flagged 204 passages (TRISO-X TR 72, core design TR 66, Long Mott SE 59, TRISO-X SE 4), skipped 0 — cost if wrong: a redaction marked some other way goes unflagged; the brackets stay visible to the model either way
58. **Task 16.** the plan's alias form "Criterion n" is replaced by "Appendix C, Criterion n" — in this corpus "Criterion n" also names the light-water GDC of 10 CFR 50 Appendix A (90 headings) and RG 1.232's ARDC; the "PDC 10" search returned GDC 10 (fuel design limits) as if it were PDC 10 (radionuclide release limits). Regression test: test_light_water_gdc_is_not_taken_for_a_pdc RED→GREEN — cost if wrong: a question saying only "Criterion 16" is not expanded to PDC 16
59. **Task 16.** layout examples quote real passages (7 quotes, all verified against the store); the regulatory_guide recipe tells the model to form codes as MHTGR-DC n / ARDC n from RG 1.232's column headers and never a bare "Criterion n", and the cfr_section recipe warns that eCFR running headers are not the paragraph's section; psar_chapter keeps its structural example because no PSAR chapter is in the pack — cost if wrong: weaker PSAR extraction once chapters are added, until the example is replaced
60. **Task 16.** 30 draft questions (24 answerable across all ten documents, 6 not-found); three not-found candidates were dropped because the corpus answers them (Long Mott cost estimate review, named project managers, ~19,000 particles per pebble — the last became q18) — cost if wrong: none until the user approves the questions
61. **Task 16.** step 5's check ("search PDC 10 returns hits from the RG and the PSAR") is not met — no PSAR is in the pack, and RG 1.232's criterion rows print the number only in a table column ("16 | Containment design."), so no alias form reaches them. Recorded with the other real-data findings for the user rather than changing the reader in Task 16 — cost if wrong: ask/test answers about MHTGR-DC n cite X-energy's restatement instead of the NRC's text until the reader labels table rows

## Deferred minors

Not fixed; listed for a later decision.

- M6 — the cost summary does not show the price-assumed or fallback flags (both are in the ledger)
- M7 rest — reviewer notes are not imported; exported cells starting with = + - @ can turn into formulas in Excel
- M8 — the search index joins passages on SQLite's implicit row ids, which a VACUUM can renumber
- M11 — a real hyphen at a line break ("pebble-\nbed") verifies as neither "pebble-bed" nor "pebblebed"

## Findings from the real NRC documents (Task 16)

These came from ingesting and searching the ten NRC documents. None costs money to fix, and none is fixed yet; together they
decide how good `ask` and `test` answers can be.

1. **A question that names a document filters out that document's own pages.** Document names (RG numbers, accession numbers,
   titles containing "Xe-100") act as text filters, but a document rarely repeats its own name. Test questions q05 (RG 1.233 on
   NEI 18-04) and q17 (which TRISO-X revision the NRC evaluated) retrieve nothing from the right document. Fix: a question naming a
   registered document searches that document's passages as well as passages citing it.
2. **Regulation paragraphs are never found by their citation.** The text of 10 CFR 50.34(a)(4) does not contain "50.34(a)(4)"
   (q07). Fix: the reader tracks the section and paragraph letters, so each paragraph carries its full citation.
3. **Citing passages crowd out the answering passage.** Search keeps the top 50 keyword matches before filtering, so passages that
   merely cite an identifier can push the one that answers out (the reviewer's "declined 12" risk, now observed).
4. **RG 1.232's criterion text is not reachable by number.** Its tables print the criterion number in a column ("16 | Containment
   design."), so a "PDC 16" or "MHTGR-DC 16" search finds X-energy's restatement but not the NRC's text. Fix: label table rows
   from the column header ("Criterion" + "MHTGR-DC Title and Content" → "MHTGR-DC 16").
5. **eCFR page headers are read as section headings.** 307 of the 324 headings found in 10 CFR 50 are running headers such as
   "10 CFR 50.33(i) (enhanced display) page 31 of 326". Passages get the wrong section label and the regulation is chunked page by
   page (331 chunks). The extraction recipe now warns the model; the reader should drop running headers.
6. **"Criterion n" was ambiguous.** In this corpus it also means the light-water GDC (10 CFR 50 Appendix A) and RG 1.232's ARDC; the
   pack now uses "Appendix C, Criterion n" (ruling above).
7. **The TRISO-X topical report is a scanned document** with OCR errors ("RlZZ", "Page SO"); redacted table cells survive only as
   bracket fragments. Noted in `outside.md`.

## Cost of the first paid run (Task 17)

| Scope | Chunks | Input tokens | Estimated cost |
|---|---|---|---|
| Everything registered | 717 | ~2.6 M | ~$32 (10 CFR 50 alone: 331 chunks) |
| RG 1.232 + X-energy PDC report + its NRC evaluation | 63 | ~0.23 M | ~$3 |

Estimates assume about 1,500 output tokens per chunk at claude-opus-5-5 prices ($4 in, $20 out per million tokens). The
budget guard plans for the worst case (16,000 output tokens per chunk), so with the $20 per-run limit a full extraction would stop
and need `--resume`.

