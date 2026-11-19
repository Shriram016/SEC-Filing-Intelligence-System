# SEC Filing Intelligence System — V3 (in progress)

A chat assistant for equity analysts that answers questions from real company filings, **with every number quoted and checked by code**, and that knows when it cannot answer.

**Status:** M0 (foundations). No answering features yet. V2 lives on the `version2` branch.

## Design

- Overview: [docs/V3_DESIGN.md](docs/V3_DESIGN.md)
- Component specs: [docs/v3/](docs/v3/)
- Decisions: [docs/adr/](docs/adr/)
- Terms: [GLOSSARY.md](GLOSSARY.md)

## Quickstart (development)

```bash
uv sync                                        # Python 3.13, locked dependencies
uv run python scripts/download_financebench.py # ~700 MB of PDFs, free
uv run python scripts/lock_financebench.py     # lock the 150 benchmark questions
uv run pytest                                  # unit tests (no API keys needed)
```

## Data credit

Uses [FinanceBench](https://github.com/patronus-ai/financebench) by Patronus AI (CC-BY-NC-4.0). The PDFs and questions are downloaded, not redistributed in this repo.
