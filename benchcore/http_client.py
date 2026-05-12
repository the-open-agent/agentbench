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
