"""Tests for the AkahuClient: auth headers, all endpoints, retries, pagination, no token leakage."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
import respx

from tests.conftest import load_fixture

# ----- auth + headers -----


async def test_includes_dual_auth_headers(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/me").mock(return_value=httpx.Response(200, json=load_fixture("me")))
    await akahu_client.get_me()
    call = respx_mock.calls.last
    assert call.request.headers["Authorization"] == "Bearer user_token_test"
    assert call.request.headers["X-Akahu-Id"] == "app_token_test"


# ----- read endpoints -----


async def test_get_me(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/me").mock(return_value=httpx.Response(200, json=load_fixture("me")))
    me = await akahu_client.get_me()
    assert me.id == "user_test_001"
    assert me.email == "test.user@example.nz"


async def test_list_accounts(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/accounts").mock(
        return_value=httpx.Response(200, json=load_fixture("accounts"))
    )
    accounts = await akahu_client.list_accounts()
    assert len(accounts) == 2
    assert accounts[0].id == "acc_chq_001"


async def test_get_account(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    data = load_fixture("accounts")
    single = {"success": True, "item": data["items"][0]}
    respx_mock.get("/accounts/acc_chq_001").mock(return_value=httpx.Response(200, json=single))
    acc = await akahu_client.get_account("acc_chq_001")
    assert acc.id == "acc_chq_001"


async def test_get_transactions(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/transactions").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    txns = await akahu_client.get_transactions()
    assert len(txns) == 3


async def test_get_transactions_with_query_params(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get("/transactions").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    await akahu_client.get_transactions(
        start="2026-05-01T00:00:00Z", end="2026-05-31T23:59:59Z"
    )
    assert route.called
    query = dict(route.calls.last.request.url.params)
    assert query["start"] == "2026-05-01T00:00:00Z"
    assert query["end"] == "2026-05-31T23:59:59Z"


async def test_get_transaction(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    data = load_fixture("transactions")
    single = {"success": True, "item": data["items"][0]}
    respx_mock.get("/transactions/txn_001").mock(return_value=httpx.Response(200, json=single))
    txn = await akahu_client.get_transaction("txn_001")
    assert txn.id == "txn_001"


async def test_iter_transactions_paginates(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    base = load_fixture("transactions")
    page_one = {
        "success": True,
        "cursor": {"next": "CURSOR_PAGE_2"},
        "items": base["items"][:2],
    }
    page_two = {
        "success": True,
        "cursor": {"next": None},
        "items": base["items"][2:],
    }

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "CURSOR_PAGE_2":
            return httpx.Response(200, json=page_two)
        return httpx.Response(200, json=page_one)

    respx_mock.get("/transactions").mock(side_effect=respond)
    collected = [t async for t in akahu_client.iter_transactions()]
    assert len(collected) == 3
    assert collected[0].id == "txn_001"
    assert collected[2].id == "txn_003"


async def test_iter_transactions_terminates_on_null_cursor(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/transactions").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    collected = [t async for t in akahu_client.iter_transactions()]
    assert len(collected) == 3


async def test_list_categories(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/categories").mock(
        return_value=httpx.Response(200, json=load_fixture("categories"))
    )
    cats = await akahu_client.list_categories()
    assert len(cats) == 3


async def test_list_connections(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/connections").mock(
        return_value=httpx.Response(200, json=load_fixture("connections"))
    )
    conns = await akahu_client.list_connections()
    assert len(conns) == 2


async def test_list_parties(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/parties").mock(
        return_value=httpx.Response(200, json=load_fixture("parties"))
    )
    parties = await akahu_client.list_parties()
    assert len(parties) == 1


# ----- write endpoints -----


async def test_refresh_all(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.post("/refresh").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    result = await akahu_client.refresh_all()
    assert result.success is True


async def test_refresh_one(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    respx_mock.post("/refresh/acc_chq_001").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    result = await akahu_client.refresh_one("acc_chq_001")
    assert result.success is True


async def test_report_transaction_issue(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.post("/support/transaction/txn_001").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    result = await akahu_client.report_transaction_issue(
        "txn_001",
        issue_type="ENRICHMENT_ERROR",
        fields=["description"],
        comment="Mislabelled merchant",
    )
    assert result.success is True
    body = route.calls.last.request.content
    assert b"ENRICHMENT_ERROR" in body
    assert b"description" in body


async def test_verify_name(akahu_client: Any, respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post("/identity/acc_chq_001/verify-name").mock(
        return_value=httpx.Response(200, json={"success": True, "item": {"matched": True}})
    )
    result = await akahu_client.verify_name("acc_chq_001", "Hemi Anderson")
    assert result.success is True
    body = route.calls.last.request.content
    assert b"Hemi Anderson" in body


# ----- retry / backoff -----


async def test_retries_on_500_then_succeeds(
    akahu_client: Any, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """500 -> 500 -> 200 must surface the 200 without raising."""
    import nz_akahu_mcp.client as client_mod

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)

    call_count = {"n": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(500, json={"success": False, "message": "server error"})
        return httpx.Response(200, json=load_fixture("me"))

    respx_mock.get("/me").mock(side_effect=respond)
    me = await akahu_client.get_me()
    assert me.id == "user_test_001"
    assert call_count["n"] == 3


async def test_retries_exhausted_raises(
    akahu_client: Any, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nz_akahu_mcp.client as client_mod

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)
    respx_mock.get("/me").mock(return_value=httpx.Response(500, json={"success": False}))
    with pytest.raises(httpx.HTTPStatusError):
        await akahu_client.get_me()


async def test_retries_on_transport_error(
    akahu_client: Any, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nz_akahu_mcp.client as client_mod

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)

    call_count = {"n": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise httpx.ConnectError("simulated drop")
        return httpx.Response(200, json=load_fixture("me"))

    respx_mock.get("/me").mock(side_effect=respond)
    await akahu_client.get_me()
    assert call_count["n"] == 2


async def test_honours_retry_after_on_429(
    akahu_client: Any, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nz_akahu_mcp.client as client_mod

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(client_mod.asyncio, "sleep", fake_sleep)

    call_count = {"n": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=load_fixture("me"))

    respx_mock.get("/me").mock(side_effect=respond)
    await akahu_client.get_me()
    assert 7.0 in sleeps


async def test_handles_missing_retry_after_header(
    akahu_client: Any, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nz_akahu_mcp.client as client_mod

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)

    call_count = {"n": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429)  # no header
        return httpx.Response(200, json=load_fixture("me"))

    respx_mock.get("/me").mock(side_effect=respond)
    await akahu_client.get_me()


async def test_handles_invalid_retry_after_header(
    akahu_client: Any, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-numeric Retry-After must not crash; we fall back to the default backoff."""
    import nz_akahu_mcp.client as client_mod

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)

    call_count = {"n": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "later"})
        return httpx.Response(200, json=load_fixture("me"))

    respx_mock.get("/me").mock(side_effect=respond)
    await akahu_client.get_me()


async def test_4xx_other_than_429_does_not_retry(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    """A 400/404 is a deterministic error - no point retrying."""
    call_count = {"n": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(404, json={"success": False, "message": "not found"})

    respx_mock.get("/me").mock(side_effect=respond)
    with pytest.raises(httpx.HTTPStatusError):
        await akahu_client.get_me()
    assert call_count["n"] == 1


# ----- logging hygiene -----


async def test_tokens_never_appear_in_logs(
    akahu_client: Any,
    respx_mock: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx_mock.get("/me").mock(return_value=httpx.Response(200, json=load_fixture("me")))
    with caplog.at_level(logging.DEBUG, logger="nz_akahu_mcp.client"):
        await akahu_client.get_me()
    blob = "\n".join(r.message for r in caplog.records)
    assert "user_token_test" not in blob
    assert "app_token_test" not in blob


async def test_logs_method_path_and_status(
    akahu_client: Any,
    respx_mock: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx_mock.get("/me").mock(return_value=httpx.Response(200, json=load_fixture("me")))
    with caplog.at_level(logging.INFO, logger="nz_akahu_mcp.client"):
        await akahu_client.get_me()
    blob = "\n".join(r.message for r in caplog.records)
    assert "GET" in blob
    assert "/me" in blob
    assert "200" in blob


# ----- aclose lifecycle -----


async def test_aclose_is_idempotent(akahu_client: Any) -> None:
    await akahu_client.aclose()
    await akahu_client.aclose()
