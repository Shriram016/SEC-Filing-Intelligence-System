# Spec — UI

**Status:** design approved (grilling 2026-11-19). Not built.
**Milestone:** M4.
**Sources:** `docs/V3_GRILLING_LOG.md` Q62, Q63, Q64, Q66, Q67. ADR-0007.

## 1. Purpose

A chat app for analysts. It talks **only to the API** over HTTP.

## 2. Tool

React (Next.js or plain React chosen at build time). Reason: industry-standard frontend, standard Keycloak/OIDC login libraries. New language (TypeScript) adds build time. Q62, ADR-0007.

## 3. Screens and features

| Feature | Detail | Ref |
|---|---|---|
| Login | Keycloak login page (username + password) | Q60, Q61 |
| Chat | Multi-turn chat; follow-up questions allowed | Q64 |
| Sidebar | Past chats on the left, like ChatGPT. Chats deleted after 30 days | Q66 |
| Live progress | Shows SSE progress events, then the checked answer streamed in parts | Q67 |
| Citations | File name, company, period, page and quoted text. No PDF viewer | Q63 |
| Special replies | Clear look for "unclear" (question back), "refused", "advice" and "not covered" replies | router.md |
| Feedback | 👍/👎 per answer | Q57 |

## 4. Not in scope

PDF viewer; file uploads (Q49); conflict side-by-side view (conflict flagging not in v1, Q15).

## 5. Tests

UI component tests; end-to-end browser tests (for example Playwright): decided at build time. Q69.

## 6. Open at build time

Next.js vs plain React; component library; design.
