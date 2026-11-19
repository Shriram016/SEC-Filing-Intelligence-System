# Spec — API service

**Status:** design approved (grilling 2026-11-19). Not built.
**Milestones:** M2 (ask + SSE + health), M4 (login, chats), M5 (full rate limits).
**Sources:** `docs/V3_GRILLING_LOG.md` Q46, Q54, Q60, Q61, Q63, Q64, Q66, Q67. ADR-0006.

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

Exact paths and schemas; rate-limit store; limit numbers; Keycloak realm setup.
