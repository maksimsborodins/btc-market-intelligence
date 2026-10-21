"""HTTP helpers: retries with backoff, per-host pacing, Binance HTTP-200 error bodies."""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import requests

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MIN_INTERVAL = 0.25          # seconds between requests to the same host
BACKOFF_BASE = 1.0
BACKOFF_MAX = 30.0

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, */*"})
_last_call: dict[str, float] = {}
_lock = threading.Lock()


class HttpError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, url: str = "", body: str = ""):
        super().__init__(message)
        self.status = status
        self.url = url
        self.body = body


class BinanceError(HttpError):
    """Binance answered HTTP 200 but with an error body {"code": ..., "msg"/"errorData": ...}."""


def _pace(host: str) -> None:
    with _lock:
        wait = _last_call.get(host, 0.0) + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()


def _backoff(attempt: int, resp=None) -> float:
    if resp is not None:
        ra = resp.headers.get("Retry-After")
        if ra and ra.isdigit():
            return min(float(ra), 120.0)
    return min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)


def _request(url: str, params, timeout: float, retries: int):
    host = urlparse(url).netloc
    last_err = "no attempt"
    status = None
    for attempt in range(retries + 1):
        _pace(host)
        resp = None
        try:
            resp = _session.get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            last_err = f"{type(e).__name__}: {e}"
            status = None
        else:
            status = resp.status_code
            if status == 429 or status == 418 or status >= 500:
                last_err = f"HTTP {status}"
            elif status >= 400:
                raise HttpError(f"HTTP {status} for {url}: {resp.text[:300]}", status, url, resp.text[:1000])
            else:
                return resp
        if attempt < retries:
            time.sleep(_backoff(attempt, resp))
    raise HttpError(f"giving up after {retries + 1} attempts for {url}: {last_err}", status, url)


def get_json(url: str, params: dict | None = None, *, timeout: float = 20, retries: int = 4):
    resp = _request(url, params, timeout, retries)
    try:
        data = resp.json()
    except ValueError as e:
        raise HttpError(f"invalid JSON from {url}: {e}", resp.status_code, url, resp.text[:300])
    if isinstance(data, dict) and "code" in data and ("msg" in data or "errorData" in data):
        raise BinanceError(f"error body from {url}: {str(data)[:300]}", resp.status_code, url, str(data)[:1000])
    return data


def get_bytes(url: str, params: dict | None = None, *, timeout: float = 60, retries: int = 4) -> bytes:
    return _request(url, params, timeout, retries).content
