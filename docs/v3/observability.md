# Spec — Observability (monitoring)

**Status:** approved (grilling 2026-11-19). Not built.
**Milestone:** M5 (basic logging from M2).
**Sources:** `docs/V3_GRILLING_LOG.md` Q46, Q51–Q53, Q56–Q58, Q71. V3_DESIGN.md 7.6.

## 1. Purpose

Show that V3 is *run*, not only built: what happened per question, how fast, how costly, and whether quality drops.

## 2. Four parts

| Part | What V3 records | Tool |
|---|---|---|
| Structured logs | Machine-readable entries, each with a request ID | Build time |
| Traces | One timeline per question: router → plan → each search → reads → checks → answer. Each step: time, cost, model, outcome, and why V3 refused or asked back | **Langfuse** |
| Metrics, dashboard, alerts | Speed (median, p95), cost per question, error rate, refusal rate, claim-check failure rate, structure-valid rate, rate-limit hits, dependency health, which model wrote the answer (Claude or OpenAI backup) | **A metrics + alerts tool** (for example Prometheus + Grafana, or hosted), chosen at build time |
| Quality monitoring | 👍/👎 per answer; automatic re-check of a sample of real answers; weekly dev eval (manual for now) | Langfuse + eval runner |

Prefer OpenTelemetry for instrumentation, so tracing is not locked to one vendor. Q56.

## 3. Alerts

- Fire when a Step 7 target is broken (error rate, cost spike, slow p95, dependency down).
- Destination: email first; a dashboard-only option is also explored. Final choice at build time. Q58.

## 4. Targets

Speed and cost targets are set **after the first measurement** (M2), with the reason written down. Load number set after the load test (M5). Q51, Q52.

## 5. Retention

Logs, traces and chats: delete after 30 days. Q46.

## 6. Portfolio note

No real on-call team. Dashboards and alerts are exercised with load-test and demo traffic; screenshots go in the README.
