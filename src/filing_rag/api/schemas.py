"""Request and SSE event models of the API (api.md §2-§3, §7; Q108).

The length limits are in the settings (limits in config, not code); the route checks them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Stage = Literal["routing", "searching", "answering", "checking"]
ErrorCode = Literal["router_failed", "answer_failed", "timeout", "cost_cap", "internal"]


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1)


class AskRequest(BaseModel):
    """One question plus the recent chat turns (oldest first). No saved chats until M4."""

    question: str = Field(min_length=1)
    history: list[TurnIn] = Field(default_factory=list)


class Citation(BaseModel):
    """Citation details only, no PDF serving (Q63)."""

    doc_name: str
    company: str | None
    doc_type: str | None
    period_end: str | None
    page: int
    quote: str


class ProgressEvent(BaseModel):
    stage: Stage


class AnswerEvent(BaseModel):
    """The checked answer, sent once after the checks (Q67). A route that stops before
    the search (unrelated, advice, unclear, not covered) is `refused` with its reply."""

    status: Literal["answer", "partial", "refused"]
    route: str
    text: str
    value: float | None = None
    unit: str | None = None
    period: str = ""
    citations: list[Citation] = Field(default_factory=list)


class DoneEvent(BaseModel):
    request_id: str
    cost_usd: float
    latency_s: float


class ErrorEvent(BaseModel):
    """Replaces `answer` and `done`. The message never holds a stack trace or a key."""

    code: ErrorCode
    message: str
    request_id: str
