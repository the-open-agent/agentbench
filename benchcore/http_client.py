from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class HttpResult:
    ok: bool
    status: int
    text: str
    latency_ms: int
    error: str | None


def chat_completion(
    base_url: str,
    model: str,
    prompt: str,
    provider_key: str,
    timeout_s: int,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/chat/completions"
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }
    t0 = time.time()
    result = post_json(url, payload, {"Authorization": f"Bearer {provider_key}"}, timeout_s)
    t1 = time.time()

    parsed = None
    parse_error = None
    assistant_text = ""
    usage = {}
    try:
        parsed = json.loads(result.text)
        usage = parsed.get("usage") or {}
        assistant_text = parsed["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        parse_error = str(exc)

    return {
        "latency_ms": int((t1 - t0) * 1000),
        "ok": result.ok and parse_error is None,
        "status": result.status,
        "error": result.error,
        "parse_error": parse_error,
        "assistant_text": assistant_text,
        "usage": usage,
    }


def health_check(base_url: str, timeout_s: int = 5) -> HttpResult:
    req = Request(url=base_url.rstrip("/") + "/api/health", method="GET")
    t0 = time.time()
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResult(True, int(getattr(resp, "status", 200)), body, int((time.time() - t0) * 1000), None)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(False, int(exc.code), body, int((time.time() - t0) * 1000), str(exc))
    except Exception as exc:  # noqa: BLE001
        return HttpResult(False, 0, "", int((time.time() - t0) * 1000), str(exc))


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: int) -> HttpResult:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers = dict(headers)
    req_headers.setdefault("Content-Type", "application/json")
    req = Request(url=url, data=body, headers=req_headers, method="POST")
    t0 = time.time()
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return HttpResult(True, int(getattr(resp, "status", 200)), text, int((time.time() - t0) * 1000), None)
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return HttpResult(False, int(exc.code), text, int((time.time() - t0) * 1000), str(exc))
    except (URLError, TimeoutError) as exc:
        return HttpResult(False, 0, "", int((time.time() - t0) * 1000), str(exc))
    except Exception as exc:  # noqa: BLE001
        return HttpResult(False, 0, "", int((time.time() - t0) * 1000), str(exc))
