# Q106 smoke test (2026-11-22, paid, approved): `chunks_v2`

Run `experiments/m2/smoke/20261122-114859`. Router Haiku 5.5 + rule A, top 5 + split-table
expansion, Sonnet 5.5 JSON answers. Questions chosen because the Q106 fixes changed them.

| ID | Fix it tests | Before (`chunks`) | Now (`chunks_v2`) |
|---|---|---|---|
| dev_0005 | Apple 10-Q p5: table cut by a long row name | gold number not in the top 10 chunks | correct, 73,347 USD million, page seen and cited |
| dev_0009 | J&J p8: lost title "Supplementary Sales Data" | evidence page not in the top 10 | correct, 7,481 USD million, page seen and cited |

Numbers correct 2/2, page in chunks 2/2, correct source cited 2/2, 0 JSON retries.
Cost $0.0150 (estimate $0.016; router $0.0005, answer $0.0145). Median 4.4 s per question.
