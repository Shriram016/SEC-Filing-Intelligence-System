# M1a step 3 — pdfplumber reader test (2026-11-19)

pdfplumber 0.11.10. 22 test pages from 5 documents (10-K, 10-Q, 8-K, earnings, annual report); no locked question uses these documents. 77 correct cells read by eye from page images (`gold_cells.json`). Scripts: `select_pages.py`, `test_reader.py`. Raw output: `results/reader_pdfplumber.json` (not committed).

## Scores (77 cells)

| Check | Plain text + word positions | Table finder, "lines" (default) | Table finder, "text" | Table finder, "text" tuned |
|---|---|---|---|---|
| Value found | **100%** | 100% | 100% | 100% |
| Value in the correct row | **100%** ¹ | 36% | 95% | 92% |
| Value under the correct column | **96%** ² | 0% | ~3% ³ | ~3% ³ |
| Time, 22 pages | ~4–7 s (≈0.3 s/page) | | | |
| Crashes | 0 | | | |

¹ Code check 96%; the 3 misses (Lockheed term sheet: "+75 basis points", "97-12+ / 3.690%", "539830 CB3") are multi-word values my check does not join. The text output has them in the correct row and column order (checked by hand).
² The 3 misses are the Lockheed table that continues on page 23: its column headers are only on page 22. Any page-by-page reader fails this.
³ The table finder splits words and numbers across cells ("2023" → "20" + "23", "9,304" → "9,3" + "04") and merges cells ("7,285 3,862"), so column headers are broken.

Column check is approximate: it checks that the column's year (or header words) is printed above the value, within 45 points horizontally. For multi-level headers it checks the lowest level only.

## Findings

1. **The text is complete and correct.** Every correct value is in the output; no wrong characters (quotes and dashes are correct Unicode). No crashes.
2. **The default table finder ("lines") fails on most filings.** These tables use shading, not ruling lines, so it finds only 38% of the values in a table.
3. **The "text" table finder finds rows but breaks columns.** Cells are cut or merged. Its output cannot be used as a clean table.
4. **Word positions keep the column information.** Using each word's x/y position, 96% of values sit under the correct header. A table builder from word positions (our own code) or the plain text line ("Net sales $ 605,881 $ 567,762 $ 555,233") keeps the order of the columns.
5. **Two-column pages are mixed.** On JPMorgan pages with two text columns, plain text joins the left and right column line by line, so sentences become wrong. A simple fix (find the empty vertical gap, read each column separately) worked on the test page; full-width headings above the columns need extra handling.
6. **Tables split over pages lose their headers** (Lockheed schedule pages 22–23). The second page needs the headers of the first page.
7. **Speed** ≈ 0.3 s per page on one CPU core. Estimate for the corpus: ≈ 50k pages → ≈ 4 h on one core, less in parallel. Not measured on the full corpus.
8. **Printed page number ≠ PDF page** (Walmart PDF page 56 shows "54").
9. The "$ printed as S" seen in the ULTA image is only how the page looks; the text has "$".

## Against the pass rule (≥ 95% of checked cells correct: value, row, unit)

- With plain text + word positions: value 100%, row 100% → **meets the rule**. Column 96%.
- With pdfplumber's own table finder: **does not meet the rule** (row 36% / 95%, column ≈ 0–3%).

The result depends on how the output is used. No decision taken; see the findings for the options.
