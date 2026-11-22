"""API smoke test (Q108): one question + one follow-up through a running server.

Records each SSE event with the time since the request started. Usage:
    uv run python experiments/m2/api_smoke/smoke.py http://127.0.0.1:8077 out.json
"""

import json
import sys
import time

import httpx

from filing_rag.api.sse import parse_sse

Q1 = (
    "What was Apple's total comprehensive income for the first nine months of fiscal 2023 "
    "(nine months ended July 1, 2023)?"
)
Q2 = "And what was its net income for the same period?"


def ask(base: str, question: str, history: list[dict[str, str]]) -> dict:
    t0 = time.monotonic()
    timed: list[dict] = []
    buf = ""
    with httpx.stream("POST", f"{base}/v1/ask", json={"question": question, "history": history},
                      timeout=90) as r:  # fmt: skip
        status = r.status_code
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                for name, data in parse_sse(block + "\n\n"):
                    timed.append({"t_s": round(time.monotonic() - t0, 3), "event": name,
                                  "data": data})  # fmt: skip
    return {"question": question, "history": history, "http_status": status, "events": timed}


def main() -> None:
    base, out = sys.argv[1], sys.argv[2]
    first = ask(base, Q1, [])
    answer = next((e["data"]["text"] for e in first["events"] if e["event"] == "answer"), "")
    second = ask(base, Q2, [{"role": "user", "text": Q1}, {"role": "assistant", "text": answer}])
    runs = [first, second]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=1, ensure_ascii=False)
    for r in runs:
        print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
