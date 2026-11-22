"""FastAPI app (api.md, Q108). Run: `uv run --group embed uvicorn filing_rag.api.app:app`.

Endpoints (M2):
- `POST /v1/ask`: one question + recent turns → SSE stream (progress..., answer, done).
- `GET /health`: the process is alive. `GET /ready`: Qdrant, catalog and key checks.
Auto-generated docs at `/docs`. Saved chats (`/v1/chats/...`) come in M4 and use the same
ask service.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from filing_rag.api.runtime import Runtime, build_runtime
from filing_rag.api.schemas import AskRequest
from filing_rag.api.service import AskService, CostMeter
from filing_rag.config import Settings, get_settings
from filing_rag.router.router import Turn

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def setup_logging() -> None:
    """Uvicorn configures only its own loggers; the per-question JSON lines need a handler."""
    logger = logging.getLogger("filing_rag")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)


def limit_problems(req: AskRequest, s: Settings) -> list[str]:
    problems = []
    if len(req.question) > s.api_max_question_chars:
        problems.append(f"question is longer than {s.api_max_question_chars} characters")
    if len(req.history) > s.api_max_history_turns:
        problems.append(f"history has more than {s.api_max_history_turns} turns")
    if any(len(t.text) > s.api_max_turn_chars for t in req.history):
        problems.append(f"a history turn is longer than {s.api_max_turn_chars} characters")
    return problems


def create_app(
    settings: Settings | None = None,
    runtime_factory: Callable[[Settings], Runtime] = build_runtime,
    cost: CostMeter | None = None,
) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        setup_logging()
        rt = runtime_factory(s)
        app.state.runtime = rt
        app.state.service = AskService(
            rt.engine, s.api_max_concurrent, s.api_timeout_s,
            cost or CostMeter(s.api_daily_cost_cap_usd),
        )  # fmt: skip
        yield

    app = FastAPI(title="Filing RAG API", version="0.2.0", lifespan=lifespan)

    @app.post(
        "/v1/ask",
        response_class=StreamingResponse,
        responses={
            200: {"content": {"text/event-stream": {}},
                  "description": "SSE: progress..., then answer + done, or error"},
            422: {"description": "invalid request or a length limit"},
            503: {"description": "busy: too many questions at the same time"},
        },
    )  # fmt: skip
    async def ask(req: AskRequest, request: Request) -> StreamingResponse:
        problems = limit_problems(req, s)
        if problems:
            raise HTTPException(status_code=422, detail=problems)
        service: AskService = request.app.state.service
        if not service.try_acquire():
            raise HTTPException(status_code=503, detail="busy, try again later",
                                headers={"Retry-After": str(s.api_retry_after_s)})  # fmt: skip
        request_id = uuid.uuid4().hex
        history = [Turn(role=t.role, text=t.text) for t in req.history]
        return StreamingResponse(
            service.stream(req.question, history, request_id),
            media_type="text/event-stream",
            headers=SSE_HEADERS | {"X-Request-ID": request_id},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        rt: Runtime = request.app.state.runtime
        checks = await asyncio.to_thread(rt.readiness)
        ok = all(checks.values())
        body: dict[str, Any] = {"ready": ok, "mode": rt.mode, "checks": checks}
        return JSONResponse(body, status_code=200 if ok else 503)

    return app


app = create_app()
