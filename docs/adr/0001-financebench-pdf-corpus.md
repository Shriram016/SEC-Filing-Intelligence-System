# ADR-0001 — FinanceBench PDFs as the only corpus

**Status:** accepted (2026-11-04). **Source:** grilling log Q2, Q3, Q4.

## Context
The old design used SEC HTML as the main source, FinanceBench PDFs as a second source, and SEC XBRL to auto-generate answer keys.

## Decision
The corpus is the 360 FinanceBench PDFs only (10-K, 10-Q, 8-K, earnings, annual reports; 2015–2024). No SEC HTML. No XBRL.

## Reasons
- FinanceBench gives a human-checked benchmark (150 open questions) whose evidence points into these exact PDFs.
- Real filings in PDF are representative of messy real-world data.
- One format: no HTML/PDF duplicate handling.

## Consequences
- The PDF reader becomes a core part; table extraction quality is the top risk.
- No automatic conflict cases (XBRL restatements) → conflict flagging leaves v1 (Q15).
- Dev answer keys are drafted by Claude and confirmed by the user (Q5).
- PDFs are on company websites: download once, keep checksums. Licence CC-BY-NC-4.0: credit FinanceBench, no commercial use.

## Rejected
SEC HTML as main source; HTML + PDF together; XBRL as answer key.
