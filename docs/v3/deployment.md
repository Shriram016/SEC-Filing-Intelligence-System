# Spec — Deployment

**Status:** deferred. Decided only after all development work is done (M7).
**Sources:** `docs/V3_GRILLING_LOG.md` Q17, Q40–Q42, Q58, Q60, Q61, Q73.

## 1. Fixed now

- A live demo is part of the final goal. Q17.
- Access: link → login page. Q40, Q60.
- Code is easy to package: settings from environment variables, no hard-coded paths, one-command start.

## 2. Parts to deploy

API, answering engine, React UI, Keycloak (+ its database), application database / vector store, Langfuse, metrics + alerts tool, local embedding model.

## 3. Hosting candidates

1. One cloud server (VM) with Docker Compose.
2. Managed cloud (AWS / GCP) with hosted database and containers.
3. Cheap platforms (for example Vercel for React, Render or Fly.io for the API).

## 4. Decisions waiting for this stage

| Item | Ref |
|---|---|
| Hosting choice and Docker setup | Q73, V3_DESIGN 8.4 |
| How recruiters get accounts (demo login, sign-up) | Q60 |
| Rate-limit numbers (first idea: about 5 questions per user per day) | Q42, Q54 |
| Keycloak hosting (needs its own server + database) | Q61 |
| Alert destination (email or dashboard) | Q58 |
| Spending caps on the Anthropic and OpenAI accounts | Q51 |
