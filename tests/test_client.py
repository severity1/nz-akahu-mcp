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
    """Wire shape must match Akahu's actual contract: /support/{txn_id} with type+other_id."""
    route = respx_mock.post("/support/txn_001").mock(
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
    assert b'"type"' in body  # not "issue_type"
    assert b"description" in body
    assert b"Mislabelled merchant" in body


async def test_report_transaction_issue_duplicate_uses_other_id(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    """DUPLICATE issue must use the 'other_id' field name in the body."""
    route = respx_mock.post("/support/txn_001").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    await akahu_client.report_transaction_issue(
        "txn_001", issue_type="DUPLICATE", other_transaction_id="txn_002"
    )
    body = route.calls.last.request.content
    assert b'"other_id"' in body  # not "other_transaction_id"
    assert b"txn_002" in body
    assert b'"other_transaction_id"' not in body


# ----- new user-scoped endpoints -----


async def test_get_pending_transactions(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/transactions/pending").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    txns = await akahu_client.get_pending_transactions()
    assert len(txns) == 3


async def test_get_account_pending_transactions(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/accounts/acc_chq_001/transactions/pending").mock(
        return_value=httpx.Response(200, json={"success": True, "items": []})
    )
    txns = await akahu_client.get_account_pending_transactions("acc_chq_001")
    assert txns == []


async def test_get_account_transactions(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get("/accounts/acc_chq_001/transactions").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    items, next_cursor = await akahu_client.get_account_transactions("acc_chq_001")
    assert len(items) == 3
    assert next_cursor is None


async def test_get_account_transactions_with_params(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    page = {"success": True, "items": [], "cursor": {"next": "CUR2"}}
    route = respx_mock.get("/accounts/acc_chq_001/transactions").mock(
        return_value=httpx.Response(200, json=page)
    )
    items, next_cursor = await akahu_client.get_account_transactions(
        "acc_chq_001", start="2026-01-01T00:00:00Z", end="2026-01-31T00:00:00Z", cursor="CUR1"
    )
    assert items == []
    assert next_cursor == "CUR2"
    qs = dict(route.calls.last.request.url.params)
    assert qs == {"start": "2026-01-01T00:00:00Z", "end": "2026-01-31T00:00:00Z", "cursor": "CUR1"}


async def test_iter_account_transactions_paginates(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    base = load_fixture("transactions")
    page1 = {"success": True, "items": base["items"][:2], "cursor": {"next": "CUR_P2"}}
    page2 = {"success": True, "items": base["items"][2:], "cursor": {"next": None}}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "CUR_P2":
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    respx_mock.get("/accounts/acc_chq_001/transactions").mock(side_effect=respond)
    collected = [t async for t in akahu_client.iter_account_transactions("acc_chq_001")]
    assert len(collected) == 3


async def test_get_transactions_by_ids(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    """Body must be a JSON array of strings, not an object."""
    route = respx_mock.post("/transactions/ids").mock(
        return_value=httpx.Response(200, json=load_fixture("transactions"))
    )
    txns = await akahu_client.get_transactions_by_ids(["txn_001", "txn_002"])
    assert len(txns) == 3
    body = route.calls.last.request.content
    # Body should be a JSON array (starts with [, not {)
    assert body.lstrip().startswith(b"[")
    assert b"txn_001" in body
    assert b"txn_002" in body


async def test_verify_name_global_path(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    """Without account_id, hits POST /verify/name (no id segment)."""
    route = respx_mock.post("/verify/name").mock(
        return_value=httpx.Response(200, json={"success": True, "item": {"matched": True}})
    )
    result = await akahu_client.verify_name(family_name="Anderson")
    assert result.success is True
    body = route.calls.last.request.content
    assert b"Anderson" in body
    assert b"family_name" in body


async def test_verify_name_account_path(
    akahu_client: Any, respx_mock: respx.MockRouter
) -> None:
    """With account_id, hits POST /verify/name/{account_id}."""
    route = respx_mock.post("/verify/name/acc_chq_001").mock(
        return_value=httpx.Response(200, json={"success": True, "item": {"matched": False}})
    )
    result = await akahu_client.verify_name(
        family_name="Anderson",
        given_name="Hemi",
        middle_name="W",
        initials=["H", "W"],
        account_id="acc_chq_001",
    )
    assert result.success is True
    body = route.calls.last.request.content
    assert b"given_name" in body
    assert b"middle_name" in body
    assert b"initials" in body


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
