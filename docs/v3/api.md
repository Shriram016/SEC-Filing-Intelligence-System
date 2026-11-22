# Spec — API service

**Status:** M2 part built (2026-11-22, Q108): `POST /v1/ask` + SSE, `/health`, `/ready`, M2 guards (§10). Login, chats and full rate limits not built.
**Milestones:** M2 (ask + SSE + health), M4 (login, chats), M5 (full rate limits).
**Sources:** `docs/V3_GRILLING_LOG.md` Q46, Q54, Q60, Q61, Q63, Q64, Q66, Q67, Q108. ADR-0006.

## 1. Purpose

The only front door. The UI and every other client talk to the API, never to the engine directly.

## 2. Endpoints (first list)

| Endpoint | Job |
|---|---|
| `POST /chats/{id}/messages` | Ask a question. Reply is an SSE stream |
| `GET /chats`, `GET /chats/{id}` | List and read the user's past chats (sidebar) |
| `POST /chats`, `DELETE /chats/{id}` | New chat, delete chat |
| `POST /messages/{id}/feedback` | 👍/👎 |
| `GET /health` | Status of AI provider, database, search index |

Auto-generated API docs. Framework: FastAPI (confirmed at build time). Exact paths fixed in M2.

## 3. SSE stream

```
event: progress  → "Searching…"
event: progress  → "Fetching chunks…"
event: progress  → "Checking quotes…"
event: answer    → the checked answer, sent in parts
event: done
event: error     → clear error message
```

The answer is streamed only **after** the quote checks pass. The user never sees an unchecked answer. Q67.

**Built (Q108):** the answer is sent as **one** `answer` event, not in parts: it exists only after the checks, so parts would only look like streaming. The live feedback is the progress events; the UI may show the text word by word. Event data (one-line JSON):

```
progress {"stage": "routing" | "searching" | "answering" | "checking"}
answer   {"status": "answer" | "partial" | "refused", "route", "text", "value", "unit",
          "period", "citations": [{"doc_name", "company", "doc_type", "period_end", "page", "quote"}]}
done     {"request_id", "cost_usd", "latency_s"}
error    {"code": "router_failed" | "answer_failed" | "timeout" | "cost_cap" | "internal",
          "message", "request_id"}        (replaces answer + done)
```

A route that stops before the search (unrelated, advice, unclear, not covered) sends its reply as `answer` with status `refused`.

## 4. Login and users

- Users log in with username + password through **Keycloak**. The API checks the Keycloak token (OIDC / JWT) on each request and reads the user ID. Q60, Q61, ADR-0006.
- How recruiters get accounts: decided in the deploy stage.

## 5. Rate limits (full production setup, demo-sized numbers)

- Per-user token bucket.
- Per-user cost budget (AI tokens per hour).
- Global limit below the AI provider account limits.
- Per-question guards: max question length, max plan steps, max total time.
- HTTP 429 with `Retry-After`.
- Limits in a shared store (for example Redis); limits in config, not code; alerts when limits are hit often.
- Numbers set in the deploy stage (first idea: about 5 questions per user per day). Q42, Q54.

## 6. Chat storage

- Store chats and messages per user in the database. Q64, Q66.
- Delete chats and logs after **30 days**. Q46, Q66.

## 7. Citations

The API returns citation details only: file name, company, period, page, quoted text. No PDF serving. Q63.

## 8. Tests

- Unit: rate limiter, token check (fake tokens), SSE event builder.
- Integration: API + fake engine + real database in CI.
- End-to-end UI/login tests: decided at build time. Q69.

## 9. Open at build time

Rate-limit store; limit numbers; Keycloak realm setup.

## 10. M2 build (Q108)

| Item | M2 decision |
|---|---|
| Ask path | `POST /v1/ask`, stateless: `{"question", "history": [{"role", "text"}]}` (at most 6 turns). M4 adds `POST /v1/chats/{id}/messages`, which reads the turns from the database and calls the same ask service |
| Health | `GET /health` = process alive. `GET /ready` = catalog loaded, Qdrant collection exists, API key set (paid mode). No call to the AI provider: a probe that depends on an outside service makes every replica "not ready" when that service is slow |
| Guards | Question ≤ 1,000 chars, turn ≤ 2,000 chars (HTTP 422); ≤ 2 questions at a time (HTTP 503 + `Retry-After`); 60 s total; daily cost cap $1 in memory. All in settings (`FILING_RAG_API_*`) |
| Paid guard | Real LLM calls only with `FILING_RAG_ALLOW_PAID=true`; else demo mode (fake router replies "unclear" with a demo message) |
| Threads | The engine is synchronous; it runs in a worker thread, progress stages come back through a queue. A timed-out question holds its slot until its thread ends; its cost still counts |
| Logs | One JSON line per question (`filing_rag.api`): request_id, route, documents, status, cost, latency, error code |
| Code | `src/filing_rag/api/` (`schemas.py`, `sse.py`, `service.py`, `runtime.py`, `app.py`). Run: `uv run --group embed uvicorn filing_rag.api.app:app` |

**Portfolio shortcuts (flagged):** the cost cap is in memory (one process; M5: shared store such as Redis); the embedding model runs inside the API process on the local GPU (production: a separate embedding service or a CPU model, decided at deploy).
