"""Server-sent events: one event = `event: <name>`, `data: <one-line JSON>`, blank line."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def sse_event(event: str, data: BaseModel | dict[str, Any]) -> str:
    payload = data.model_dump() if isinstance(data, BaseModel) else data
    # json.dumps never writes a raw newline, so the data stays on one line
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Read an SSE body back into (event, data) pairs (for tests and the smoke test)."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data += line[len("data:") :].strip()
        if data:
            events.append((name, json.loads(data)))
    return events
