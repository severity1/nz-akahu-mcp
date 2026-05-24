"""Targeted tests to hit the last few uncovered branches."""

from __future__ import annotations

import httpx
import pytest
import respx

from tests.conftest import load_fixture

# ---------- client: __aenter__ / __aexit__ ----------


async def test_client_async_context_manager(
    fake_env: None, respx_mock: respx.MockRouter
) -> None:
    """The client should be usable as `async with AkahuClient() as c:`."""
    from nz_akahu_mcp.client import AkahuClient
    from nz_akahu_mcp.config import AkahuConfig

    respx_mock.get("/me").mock(return_value=httpx.Response(200, json=load_fixture("me")))
    async with AkahuClient(AkahuConfig()) as client:
        me = await client.get_me()
    assert me.id == "user_test_001"


# ---------- client: transport-error exhausted ----------


async def test_client_transport_error_exhausted(
    fake_env: None, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If every attempt raises TransportError, the last exception must bubble up."""
    import nz_akahu_mcp.client as client_mod
    from nz_akahu_mcp.client import AkahuClient
    from nz_akahu_mcp.config import AkahuConfig

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)
    respx_mock.get("/me").mock(side_effect=httpx.ConnectError("down"))

    client = AkahuClient(AkahuConfig())
    try:
        with pytest.raises(httpx.ConnectError):
            await client.get_me()
    finally:
        await client.aclose()


# ---------- client: get_transactions with cursor ----------


async def test_get_transactions_with_cursor_param(
    fake_env: None, respx_mock: respx.MockRouter
) -> None:
    """The explicit cursor argument on get_transactions should land in the URL."""
    from nz_akahu_mcp.client import AkahuClient
    from nz_akahu_mcp.config import AkahuConfig

    route = respx_mock.get("/transactions").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    client = AkahuClient(AkahuConfig())
    try:
        await client.get_transactions(cursor="OPAQUE_CURSOR_ABC")
    finally:
        await client.aclose()
    assert dict(route.calls.last.request.url.params)["cursor"] == "OPAQUE_CURSOR_ABC"


# ---------- client: iter_transactions with start+end ----------


async def test_iter_transactions_passes_start_end(
    fake_env: None, respx_mock: respx.MockRouter
) -> None:
    from nz_akahu_mcp.client import AkahuClient
    from nz_akahu_mcp.config import AkahuConfig

    route = respx_mock.get("/transactions").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    client = AkahuClient(AkahuConfig())
    try:
        _ = [
            t
            async for t in client.iter_transactions(
                start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z"
            )
        ]
    finally:
        await client.aclose()
    params = dict(route.calls.last.request.url.params)
    assert params["start"] == "2026-01-01T00:00:00Z"
    assert params["end"] == "2026-01-31T23:59:59Z"


# ---------- client: report_transaction_issue with only the minimum body ----------


async def test_report_issue_minimal_body(
    fake_env: None, respx_mock: respx.MockRouter
) -> None:
    """If fields/comment/other are all absent, the body must only have type."""
    from nz_akahu_mcp.client import AkahuClient
    from nz_akahu_mcp.config import AkahuConfig

    route = respx_mock.post("/support/txn_a").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    client = AkahuClient(AkahuConfig())
    try:
        await client.report_transaction_issue("txn_a", issue_type="DUPLICATE")
    finally:
        await client.aclose()
    body = route.calls.last.request.content
    assert b"DUPLICATE" in body
    assert b"fields" not in body
    assert b"comment" not in body
    assert b"other_id" not in body


async def test_report_issue_with_other_id(
    fake_env: None, respx_mock: respx.MockRouter
) -> None:
    """The other_id field (not other_transaction_id) must land in the request body."""
    from nz_akahu_mcp.client import AkahuClient
    from nz_akahu_mcp.config import AkahuConfig

    route = respx_mock.post("/support/txn_a").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    client = AkahuClient(AkahuConfig())
    try:
        await client.report_transaction_issue(
            "txn_a", issue_type="DUPLICATE", other_transaction_id="txn_b"
        )
    finally:
        await client.aclose()
    body = route.calls.last.request.content
    assert b'"other_id"' in body
    assert b"txn_b" in body
    assert b'"other_transaction_id"' not in body


# ---------- deps: real construction + close ----------


async def test_deps_constructs_real_client_and_closes(fake_env: None) -> None:
    """Exercise deps.get_client() and aclose_client() with no monkeypatch."""
    from nz_akahu_mcp import deps

    # Module-level state may have leaked from earlier tests; reset.
    deps._client = None
    try:
        client_one = deps.get_client()
        client_two = deps.get_client()
        assert client_one is client_two  # cached
    finally:
        await deps.aclose_client()
    assert deps._client is None
    # aclose on already-empty state is a no-op.
    await deps.aclose_client()
