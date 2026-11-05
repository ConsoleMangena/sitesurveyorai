"""CORS policy tests for the API and MCP surfaces.

`allow_origins=["*"]` with `allow_credentials=True` is the configuration that looks like
"it works for everyone" and is actually "any website can make credentialed calls here and
read the answers". The MCP SSE transport had the same wildcard, which the SDK only enforces
when DNS-rebinding protection is on -- so the origin check lives here instead.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest

import src.api as api


# ---------------------------------------------------------------------------
# Origin list parsing
# ---------------------------------------------------------------------------

def test_no_wildcard_mode_exists(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    assert api._allowed_origins() == []


def test_origins_are_trimmed_and_blanks_dropped(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://a.example , ,https://b.example,")
    assert api._allowed_origins() == ["https://a.example", "https://b.example"]


def test_plain_http_origin_is_kept_but_warned(monkeypatch, caplog):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://insecure.example")
    with caplog.at_level("WARNING", logger="sitesurveyor.api"):
        assert api._allowed_origins() == ["http://insecure.example"]
    assert any("not https" in r.message for r in caplog.records)


def test_middleware_is_absent_when_no_origins_are_configured():
    """The bundled sandbox fetches /api/* same-origin, so no CORS layer is the correct
    default -- and its absence is what stops arbitrary origins reading responses."""
    assert not any(m.cls.__name__ == "CORSMiddleware" for m in api.app.user_middleware)


def test_middleware_is_installed_for_configured_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example")
    try:
        reloaded = importlib.reload(api)
        cors = [m for m in reloaded.app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
        assert len(cors) == 1
        assert cors[0].kwargs["allow_origins"] == ["https://app.example"]
        assert "*" not in cors[0].kwargs["allow_origins"]
    finally:
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        importlib.reload(api)


# ---------------------------------------------------------------------------
# Same-origin detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("origin,host,expected", [
    ("http://127.0.0.1:8000", "127.0.0.1:8000", True),
    ("https://app.example", "app.example", True),          # port omitted on 443
    ("http://localhost:3000", "localhost:8000", False),    # different port = different origin
    ("https://evil.example", "127.0.0.1:8000", False),
    ("null", "127.0.0.1:8000", False),                     # sandboxed/file context Origin
    ("http://127.0.0.1:8000", None, False),
])
def test_same_origin_only_when_the_page_calls_its_own_host(origin, host, expected):
    assert api._is_same_origin(origin, host) is expected


# ---------------------------------------------------------------------------
# MCP SSE origin guard
# ---------------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1


async def _run_guard(scope_headers, allowed):
    inner = _Recorder()
    guard = api._OriginGuard(inner, set(allowed))
    status: list[int] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status.append(message["status"])

    scope = {"type": "http", "method": "GET", "path": "/sse", "headers": scope_headers}
    await guard(scope, receive, send)
    return status, inner.calls


def test_guard_refuses_foreign_origin_and_passes_the_rest():
    """Driven with asyncio.run so the suite needs no async plugin."""
    headers = [(b"origin", b"https://evil.example")]
    status, calls = asyncio.run(_run_guard(headers, []))
    assert status == [403] and calls == 0, "a foreign browser origin reached the MCP app"

    same_origin = [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")]
    status, calls = asyncio.run(_run_guard(same_origin, []))
    assert status == [] and calls == 1, "the bundled page was blocked from calling its own host"

    native_agent = [(b"host", b"127.0.0.1:8000")]
    status, calls = asyncio.run(_run_guard(native_agent, []))
    assert status == [] and calls == 1, "a desktop MCP client sends no Origin and must pass"

    configured = [(b"origin", b"https://app.example"), (b"host", b"127.0.0.1:8000")]
    status, calls = asyncio.run(_run_guard(configured, ["https://app.example"]))
    assert status == [] and calls == 1, "an explicitly allowed origin was refused"
