# M1b label check (2026-11-20)

Chunk label = `Company type year › section › subsection › heading` (+ table title for tables).
Corpus: 22 documents, 8,568 chunks (run 3). Script: `label_audit.py`; verdicts: `label_audit.json`.

## Check 1 — automatic rules (all 8,568 chunks)

Rules: Item order, notes only in financial sections, note numbering, heading shape, table-title shape, long spans.
First run: 156 flags, all false alarms of two rules (numbered lists restarting at 1; one heading appearing twice far apart). After fixing the two rules: **0 flags**.
Safety rule ("leave it out when unsure") rejected 18 headings in the run.

## Check 2 — hand-check of 50 random chunks

Sample: 2 chunks per document + 6 more, seed 20261120. Evidence: page text from a second reader (pypdfium2), the last Item/Note/Exhibit line before the chunk (independent scan), page images for unclear cases.

| Label part | Correct | Pass rule | Result |
|---|---|---|---|
| Company, type, year | 50 / 50 (100%) | 100% | **Pass** |
| Section (Item / Exhibit) | 48 / 50 (96%) | ≥ 95% | **Pass** |
| Subsection (note / major heading) | 41 / 50 (82%) | — | Low |
| Heading (minor heading) | 42 / 50 (84%) | — | Low |
| Table title (12 tables) | 6 correct, 4 wrong, 2 missing | — | Low |
| **Full path correct** (all parts) | **33 / 50 (66%)** | ≥ 95% | **Fail** |

## Causes of the errors

| Cause | Chunks | Example |
|---|---|---|
| **A. Stale subsection:** a new heading was missed, so the old one carries on | 8, 21, 31, 37, 41, 44 | Intel p86: page is NOTE 6, label says NOTE 5 (NOTE 6 line absorbed into a table header). Apple/Verizon agreements: run-in numbered headings ("12. Electronic Delivery. The Company …") are not found |
| **B. Wrong text taken as a heading** | 6, 13, 19, 23, 24, 32, 36, 37, 39, 43 | column headers ("(Unaudited) (Unaudited) Assets"), form fields ("CUSIP [•]", telephone line), party names in signature blocks, a lower-case sentence fragment, spaced capital letters |
| **C. Wrong section** | 38, 50 | "Exhibit 4.1)" in an exhibit list taken as an exhibit heading; back pages after the last exhibit |
| **D. Wrong table title** | 19, 38, 39, 50 | the first row label or a bullet line used as the title |

Also seen: a heading followed by a table becomes a tiny chunk of its own (chunks 29, 42).

## Planned fixes (free, code only)

1. A Note line ("NOTE 6 : …") is never a table header.
2. An Exhibit heading must be a whole line ("Exhibit 4.1" + short title), not a list entry; 8-K item codes also in documents listed as earnings.
3. Heading shape: no lower-case start, no spaced single letters, no form-field lines, no column-header lines.
4. Run-in headings: a bold or numbered start of a paragraph ("12. Electronic Delivery.") is a heading.
5. Table title: prefer the heading or statement title above the table; never a row label or bullet.
6. A heading directly followed by a table goes into the table chunk, not into a chunk of its own.
7. Safety: a subsection taken from a cover page, signature block or party name is not used.

Re-test with a **new** random sample of 50 (new seed), so the fixes are not tuned to this sample.

---

# Round 2 (after fixes 1–7 and 3 more from the automatic checks)

Run 5: 8,415 chunks, 0 over the token limit, 54 doubtful headings left out (safety rule). Automatic checks: 2 flags, both checked and correct (Amcor "Article I" definitions span 36 pages).
Hand-check: **new** sample of 50 (seed 20261121), verdicts in `label_audit_r2.json`.

| Label part | Round 1 | Round 2 |
|---|---|---|
| Company, type, year | 50 / 50 | 50 / 50 |
| Section (Item / Exhibit) | 48 / 50 | 46 / 50 |
| Subsection | 41 / 50 | 44 / 50 |
| Heading (minor) | 42 / 50 | 43 / 50 |
| Table title correct (of 12) | 6 | 7 (3 missing) |
| **Full path correct** | **33 / 50 (66%)** | **36 / 50 (72%)** |
| Full path without the minor heading | 37 / 50 (74%) | 41 / 50 (82%) |

The round-1 fixes worked (no repeat of the round-1 error types except stale headings), but the new sample shows **new** error types. This is a long tail:

| New cause | Chunks |
|---|---|
| Long Item titles rejected by the word limit (Costco "Item 7 … (amounts in millions …)", 8-K Item 5.02 on 2 lines) | 11, 13 |
| Exhibits after Item 16 / signatures with no "Exhibit" heading | 45, 46 |
| Page header "NOTES … —(Continued)" taken as a new subsection | 36 |
| Column-header fragments ("13 Weeks Ended", "Sales to customers by") | 26, 40 |
| Plain-text statement title not found; company name as heading | 30 |
| Cover fields ("DELAWARE 88-0215232", "Date of Report …") | 14, 33 |
| Stale minor heading (sub-heading style not found) | 4, 49 |
| Defined term as heading ("SOFR"); sentence fragment "(50%) by reason …" | 6, 45 |
| Row label inside a statement used as table title | 35 |

---

# Decision after round 2 (Q99)

Label tuning stopped. The embedded label is now **company, type, period + section**. Subsection, heading and table title are stored, not embedded.

| Part | Both rounds (100 chunks) | Found by | Embedded? |
|---|---|---|---|
| Company, type, year | 100% | document list + cover page | yes |
| Section | 94% | fixed SEC patterns | yes |
| Subsection | 85% | pattern or font style | no (stored) |
| Heading | 85% | font style only | no (stored) |

M1d measures `label_depth` = `none` / `section` / `full` on the dev set.

## Section fixes (run 7, 8,282 chunks, 0 over the limit, 2 correct `long_span` flags)

| Fix | Effect |
|---|---|
| Item check before the 14-word heading limit and the "ends with ," rule | Item 5 (long official title) now found in 3M, Apple, CVS, Oracle, Verizon, Costco; Costco Item 7; Costco 8-K Item 5.02; Amcor Item 2.03; Apple 10-Q Part II Item 2 |
| Brackets removed before the title word count; limit 16 → 24 | Costco "Item 7 … (amounts in millions, …" |
| "Exhibit 10.5(40)" accepted | MGM exhibits after Item 16 now labelled Exhibit 10.5 (chunks 45, 46) |
| First letter of the Item title must be a capital | blocks "Item 9A, management excluded …" (Adobe; found by the before/after page diff) |

Round-2 section errors: 4 of 4 fixed (chunks 11, 13, 45, 46). Known left: wrapped line "Exhibit 95 to this annual report." (3M p13, 1 chunk).
Check method: section of every page saved before the change and compared after it; every changed page was looked at.
