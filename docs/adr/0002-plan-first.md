# ADR-0002 — Plan first, not an agent loop

**Status:** accepted (2026-11-18). **Source:** grilling log Q28.

## Context
Finance questions need several steps (find, find, calculate, compare). Options: fixed template (V2), plan first, agent loop.

## Decision
Plan first: one LLM call writes the steps; code runs them; at most one re-plan. Consider an agent loop only if plan-first fails for most cases.

## Reasons
- Finance question steps are predictable.
- Fixed, known cost and speed per question.
- Safety: the plan is made from the question alone, before any document is read.
- Easy debugging: each step can fail and be tagged on its own.

## Consequences
Less flexible for unusual questions. No up-front plan-first vs agent-loop test (comparison only on need).

## Rejected
Agent loop as default (variable cost, can loop, harder to test); fixed template (cannot do calculate / explain why).
