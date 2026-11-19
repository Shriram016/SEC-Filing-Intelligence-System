# ADR-0005 — Claude for the pipeline, OpenAI for judge and backup

**Status:** accepted (2026-11-18/19). **Source:** grilling log Q35–Q38, Q53.

## Decision
| Job | Model |
|---|---|
| Router | Claude Haiku 5.5 |
| Planner, fact reading, answer writer | Claude Sonnet 5.5 (for now) |
| Eval judge | An OpenAI model (build time) |
| Backup when Claude is down | An OpenAI model (build time) |
| Embeddings | Free local model (build time) |

One swappable model layer: a model change is a config change.

## Reasons
Model per job controls cost. A judge from a different family reduces "marking its own homework". A second provider survives a provider outage.

## Consequences
Cost targets set after the first measurement (Sonnet is far above the old Groq numbers). Answers written by the OpenAI backup are judged by the same family: log which model wrote each answer.

## Rejected
Groq (old plan); one model for everything; paid embeddings.
