"""Tests for the identity sub-server: 3 read + 1 write (always elicits)."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from nz_akahu_mcp.models import Category, Me, Party, VerifyNameResult
from tests.conftest import load_fixture


@pytest.fixture
def patched_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    from nz_akahu_mcp import deps

    me = Me.model_validate(load_fixture("me")["item"])
    parties = [Party.model_validate(i) for i in load_fixture("parties")["items"]]
    cats = [Category.model_validate(i) for i in load_fixture("categories")["items"]]
    client = MagicMock()
    client.get_me = AsyncMock(return_value=me)
    client.list_parties = AsyncMock(return_value=parties)
    client.list_categories = AsyncMock(return_value=cats)
    client.verify_name = AsyncMock(
        return_value=VerifyNameResult(success=True, item={"matched": True})
    )
    monkeypatch.setattr(deps, "get_client", lambda: client)
    return client


# ---------- get_me ----------


async def test_get_me(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.identity import get_me

    result = await get_me()
    assert result["id"] == "user_test_001"
    assert result["email"] == "test.user@example.nz"
    assert result["name"] == "Hemi Anderson"


async def test_get_me_no_profile(fake_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.identity import get_me

    me = Me.model_validate({"_id": "u1", "email": "x@y", "profile": None})
    client = MagicMock()
    client.get_me = AsyncMock(return_value=me)
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_me()
    assert result["name"] is None


# ---------- list_parties ----------


async def test_list_parties(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.identity import list_parties

    result = await list_parties()
    assert len(result["parties"]) == 1
    assert result["parties"][0]["name"] == "Hemi Anderson"


# ---------- list_categories ----------


async def test_list_categories(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.identity import list_categories

    result = await list_categories()
    assert len(result["categories"]) == 3
    assert all("id" in c and "name" in c for c in result["categories"])


# ---------- verify_name (write, always elicits) ----------


async def test_verify_name_blocks_in_readonly(
    fake_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ReadOnlyError
    from nz_akahu_mcp.tools.identity import verify_name

    ctx = ctx_factory()
    with pytest.raises(ReadOnlyError):
        await verify_name(ctx=ctx, account_id="acc_chq_001", name="Hemi Anderson")


async def test_verify_name_accept(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.identity import verify_name

    ctx = ctx_factory(elicit_action="accept")
    result = await verify_name(ctx=ctx, account_id="acc_chq_001", name="Hemi Anderson")
    assert result["success"] is True
    patched_client.verify_name.assert_awaited_once_with("acc_chq_001", "Hemi Anderson")
    msg = ctx.elicit.await_args[0][0]
    assert "Hemi Anderson" in msg
    assert "acc_chq_001" in msg


async def test_verify_name_decline(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.identity import verify_name

    ctx = ctx_factory(elicit_action="decline")
    with pytest.raises(ElicitationDeclinedError):
        await verify_name(ctx=ctx, account_id="acc_chq_001", name="Hemi")


async def test_verify_name_cancel(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.identity import verify_name

    ctx = ctx_factory(elicit_action="cancel")
    with pytest.raises(ElicitationDeclinedError):
        await verify_name(ctx=ctx, account_id="acc_chq_001", name="Hemi")


async def test_verify_name_still_elicits_under_bypass(
    bypass_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    """Not marked automatable -> bypass must not skip elicit."""
    from nz_akahu_mcp.tools.identity import verify_name

    ctx = ctx_factory(elicit_action="accept")
    await verify_name(ctx=ctx, account_id="acc_chq_001", name="Hemi")
    ctx.elicit.assert_awaited_once()


async def test_server_registers_four_tools(fake_env: None) -> None:
    from nz_akahu_mcp.tools.identity import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {"get_me", "list_parties", "list_categories", "verify_name"}
