# ADR-0003 — Code does the maths and checks the quotes

**Status:** accepted (2026-11-18). **Source:** grilling log Q29, Q30, Q31, Q32.

## Context
LLMs make arithmetic errors and sometimes cite sources that do not say what is claimed. In finance, a wrong number that looks cited is worse than no answer.

## Decision
1. A calculator tool in code does all arithmetic. The LLM only picks the formula and the cited inputs.
2. The LLM returns structured JSON: claims, each with an exact quote and a chunk ID.
3. Code checks each quote exists in the chunk and each number appears in the quote or comes from the calculator. Failed claims are removed.
4. Broken JSON: retry once, then a clear error.

## Reasons
Code checks are reliable, cheap and testable. This is the quote-level grounding used in high-trust domains.

## Consequences
More prompt and schema work; some correct but badly quoted claims are removed. The answer cannot stream word by word before the check (SSE streams the checked answer, Q67).

## Rejected
Free prose with [N] markers checked by an AI judge; sources listed only (V2); LLM arithmetic.
