# ADR-0004 — A router before search

**Status:** accepted (2026-11-18). **Source:** grilling log Q33, Q34, Q48.

## Context
Three kinds of "cannot answer": off-topic; data not in the collection; data present but search missed it. The second must be known before search, or a retrieval miss looks like a correct refusal.

## Decision
A separate router runs first: one cheap LLM call (Claude Haiku 5.5) with JSON output, then a **code** coverage check against a document catalog built from the 361 PDFs. Routes: unrelated, advice, not_covered, unclear, answer.

## Reasons
Stops bad questions cheaply and early; makes "no filing for that period" exact; separates correct refusals from retrieval failures in evals.

## Consequences
One extra LLM call per question (cheap model). New rule: no further LLM calls are added without measured need (Q65).

## Rejected
Letting the planner or the answer writer decide refusals; a decision-model API (Jev).
