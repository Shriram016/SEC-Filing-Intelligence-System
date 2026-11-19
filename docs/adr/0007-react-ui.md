# ADR-0007 — React for the UI

**Status:** accepted (2026-11-19). **Source:** grilling log Q62.

## Decision
React (Next.js or plain React chosen at build time). The UI talks only to the API.

## Reasons
Industry-standard frontend; standard Keycloak/OIDC libraries; a ChatGPT-style chat with sidebar and SSE streaming is natural in React.

## Consequences
New language and toolset (TypeScript) adds build time (planned in M4).

## Rejected
Streamlit (V2): fast to build, but weak login support and less product-like.
