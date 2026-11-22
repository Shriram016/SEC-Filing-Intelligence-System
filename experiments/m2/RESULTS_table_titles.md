# Q105 small test: table title in the embedded text (2026-11-22, free)

Setup: the 21 dev-set evidence documents re-ingested with the fix into the test collection
`chunks_t105` (ingest folder `data/v3_t105`). Compared with `chunks` inside the gold document
(same 50 questions, k = 10). Script: `experiments/m2/table_titles/compare.py`; output:
`experiments/m2/table_titles/old_chunks/`, `.../small_titles/`.

## Ingestion check

- 21/21 documents OK, 0 chunks over the limit (max 480 tokens), 0 duplicate ids.
- Text chunks: identical to `chunks` (6,742; same ids and embedded text).
- Table chunks: 1,534 → 1,543 (the title takes room, so 9 tables got one more part).
- 980 of 1,543 table chunks have a title (64%); all 980 now have it in the embedded text.

## Search, gold document

| Group | Hit@5 old → new | Hit@10 old → new | MRR old → new | Value@5 old → new |
|---|---|---|---|---|
| all (50) | 0.70 → 0.70 | 0.74 → 0.78 | 0.586 → 0.580 | 0.65 → 0.65 (n 20) |
| table (28) | 0.607 → 0.607 | 0.643 → 0.714 | 0.477 → 0.467 | 0.60 → 0.60 (n 10) |
| text (22) | 0.818 → 0.818 | 0.864 → 0.864 | 0.725 → 0.725 | 0.70 → 0.70 (n 10) |

Changed questions: better dev_0002, dev_0007, dev_0037 (miss → 6), dev_0041 (miss → 8),
dev_0044 (7 → 3); worse dev_0003 (2 → 4), dev_0032 (2 → 3), dev_0050 (2 → 9), dev_0013 (value
2 → 3). **Verdict: no gain at Hit@5** (rule set before the run: go only if tables improve).

## Why the title did not help (checked by hand)

1. **Computed metrics:** dev_0032 asks for "operating margin"; the table holds "Operating
   income" and "Revenues". The titled "KEY FINANCIAL METRICS" chunk is still not in the top 5.
2. **Score too strict:** dev_0004 (Apple services revenue 2019): the gold page is p32, but the
   p40 table at rank 3 also holds the number (46,291). The page check counts it as a miss.
3. **Title not found:** 36% of table chunks have no title. dev_0009 (J&J MedTech): the title
   "Supplementary Sales Data" went into a separate text chunk; the table chunk says "Table."

## Split-table expansion (same test, old `chunks`, rule A)

- It adds parts for 8 of 50 questions (19 chunks; +10% characters in the top 5).
- It does **not** fix the 3 baseline "split table" errors (dev_0005, dev_0038, dev_0043): those
  tables are not row groups of one `table_id`. The PDF reader cut one table into separate
  tables (Apple 10-Q p5: a row "Change in unrealized gains/losses…" was taken as the title of a
  second table).
- For the find-number questions, it never brought the gold number into the top 5.

## Next options (for the user to decide)

- Keep the rule "embedded text = label + answer text" in the code (correct, no loss, Hit@10
  +0.07 for tables), but do not re-ingest now; it comes in with the next re-ingestion.
- Real causes to work on: the table-cut in the PDF reader (blocks.py join rule), title
  detection, and multiple valid evidence pages in the score. A reranker or BM25 (Q26, Q27) for
  "computed metric" questions.
