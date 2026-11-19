# ADR-0006 — Keycloak for login

**Status:** accepted (2026-11-19). **Source:** grilling log Q60, Q61.

## Context
Per-user rate limits and chat history need a user identity. V3 is treated as a real product.

## Decision
Username + password login through Keycloak (open-source, self-hosted). The API validates the Keycloak token (OIDC / JWT) and reads the user ID.

## Reasons
No home-made password handling: Keycloak gives hashing, reset, brute-force protection and standard tokens.

## Consequences
Keycloak needs its own server and database at deploy time. Recruiter access is decided in the deploy stage.

## Rejected
IP address; a key per link; building password login in the API; hosted providers (Auth0, Clerk, Supabase) were possible but not chosen.
