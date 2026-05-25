"""Tests for safety.py: ReadOnlyError, elicit gating, automation bypass."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest


async def test_confirm_write_proceeds_on_accept(
    fake_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import confirm_write

    ctx = ctx_factory(elicit_action="accept")
    await confirm_write(ctx, "Do the thing?")
    ctx.elicit.assert_awaited_once()
    args, kwargs = ctx.elicit.call_args
    assert "Do the thing?" in args[0]


async def test_confirm_write_raises_on_decline(
    fake_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError, confirm_write

    ctx = ctx_factory(elicit_action="decline")
    with pytest.raises(ElicitationDeclinedError):
        await confirm_write(ctx, "Do the thing?")


async def test_confirm_write_raises_on_cancel(
    fake_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import ElicitationCancelledError, confirm_write

    ctx = ctx_factory(elicit_action="cancel")
    with pytest.raises(ElicitationCancelledError):
        await confirm_write(ctx, "Do the thing?")


async def test_confirm_write_passes_explicit_response_type(
    fake_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    """Lock in the FastMCP 3.3 deprecation fix: never pass response_type=None."""
    from nz_akahu_mcp.safety import confirm_write

    ctx = ctx_factory(elicit_action="accept")
    await confirm_write(ctx, "Do the thing?")
    _, kwargs = ctx.elicit.call_args
    assert kwargs.get("response_type") is not None


def test_cancelled_error_is_a_declined_error() -> None:
    """Subclass relationship lets binary 'did the user consent?' handlers
    catch both outcomes via `except ElicitationDeclinedError`."""
    from nz_akahu_mcp.safety import (
        ElicitationCancelledError,
        ElicitationDeclinedError,
    )

    assert issubclass(ElicitationCancelledError, ElicitationDeclinedError)


async def test_require_write_consent_blocks_in_readonly(
    fake_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    """fake_env defaults to read-only; the decorated tool must refuse."""
    from nz_akahu_mcp.safety import ReadOnlyError, require_write_consent

    @require_write_consent("Do the thing")
    async def my_tool(*, ctx: Any, value: int) -> int:
        return value * 2  # pragma: no cover  # why: should not run when read-only

    ctx = ctx_factory()
    with pytest.raises(ReadOnlyError) as exc_info:
        await my_tool(ctx=ctx, value=21)
    msg = str(exc_info.value)
    assert "AKAHU_READ_ONLY" in msg
    assert "AKAHU_AUTOMATION_BYPASS" in msg
    ctx.elicit.assert_not_awaited()


async def test_require_write_consent_elicits_and_runs(
    writable_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import require_write_consent

    @require_write_consent("Do the thing")
    async def my_tool(*, ctx: Any, value: int) -> int:
        return value * 2

    ctx = ctx_factory(elicit_action="accept")
    result = await my_tool(ctx=ctx, value=21)
    assert result == 42
    ctx.elicit.assert_awaited_once()


async def test_require_write_consent_aborts_on_decline(
    writable_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError, require_write_consent

    @require_write_consent("Do the thing")
    async def my_tool(*, ctx: Any, value: int) -> int:
        return value * 2  # pragma: no cover  # why: decline short-circuits

    ctx = ctx_factory(elicit_action="decline")
    with pytest.raises(ElicitationDeclinedError):
        await my_tool(ctx=ctx, value=21)


async def test_require_write_consent_aborts_on_cancel(
    writable_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import ElicitationCancelledError, require_write_consent

    @require_write_consent("Do the thing")
    async def my_tool(*, ctx: Any, value: int) -> int:
        return value * 2  # pragma: no cover  # why: cancel short-circuits

    ctx = ctx_factory(elicit_action="cancel")
    with pytest.raises(ElicitationCancelledError):
        await my_tool(ctx=ctx, value=21)


async def test_automatable_skips_elicit_when_bypass_on(
    bypass_env: None,
    ctx_factory: Callable[..., MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    from nz_akahu_mcp.safety import require_write_consent

    @require_write_consent("Refresh things", automatable=True)
    async def my_tool(*, ctx: Any, value: int) -> int:
        return value * 2

    ctx = ctx_factory(elicit_action="decline")  # decline ignored when bypassed
    with caplog.at_level(logging.INFO, logger="nz_akahu_mcp.safety"):
        result = await my_tool(ctx=ctx, value=21)
    assert result == 42
    ctx.elicit.assert_not_awaited()
    assert any("[BYPASS]" in r.message and "my_tool" in r.message for r in caplog.records)


async def test_automatable_still_elicits_when_bypass_off(
    writable_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import require_write_consent

    @require_write_consent("Refresh things", automatable=True)
    async def my_tool(*, ctx: Any, value: int) -> int:
        return value * 2

    ctx = ctx_factory(elicit_action="accept")
    result = await my_tool(ctx=ctx, value=21)
    assert result == 42
    ctx.elicit.assert_awaited_once()


async def test_non_automatable_still_elicits_when_bypass_on(
    bypass_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import require_write_consent

    @require_write_consent("Sensitive write", automatable=False)
    async def my_tool(*, ctx: Any, value: int) -> int:
        return value * 2

    ctx = ctx_factory(elicit_action="accept")
    result = await my_tool(ctx=ctx, value=21)
    assert result == 42
    ctx.elicit.assert_awaited_once()


def test_bypass_eligible_tools_registry(fake_env: None) -> None:
    """Decorator records its name iff automatable=True; non-automatable absent."""
    from nz_akahu_mcp import safety
    from nz_akahu_mcp.safety import bypass_eligible_tools, require_write_consent

    # Snapshot/restore to avoid polluting other tests that rely on real tool registrations.
    snapshot = set(safety._BYPASS_REGISTRY)  # noqa: SLF001
    try:

        @require_write_consent("auto thing", automatable=True)
        async def auto_thing(*, ctx: Any) -> None: ...  # pragma: no cover

        @require_write_consent("manual thing", automatable=False)
        async def manual_thing(*, ctx: Any) -> None: ...  # pragma: no cover

        names = bypass_eligible_tools()
        assert "auto_thing" in names
        assert "manual_thing" not in names
    finally:
        safety._BYPASS_REGISTRY.clear()  # noqa: SLF001
        safety._BYPASS_REGISTRY.update(snapshot)  # noqa: SLF001


def test_action_description_renders_kwargs(fake_env: None) -> None:
    """The {placeholders} in the action description must format from call kwargs."""
    from nz_akahu_mcp.safety import render_action_description

    rendered = render_action_description(
        "Refresh data for account {account_id}.",
        {"account_id": "acc_123"},
    )
    assert rendered == "Refresh data for account acc_123."


def test_action_description_tolerates_extra_kwargs(fake_env: None) -> None:
    from nz_akahu_mcp.safety import render_action_description

    rendered = render_action_description(
        "Refresh data for account {account_id}.",
        {"account_id": "acc_123", "extra": "ignored"},
    )
    assert rendered == "Refresh data for account acc_123."


def test_action_description_tolerates_missing_kwargs(fake_env: None) -> None:
    """If the template references a kwarg that wasn't passed, leave it as a literal."""
    from nz_akahu_mcp.safety import render_action_description

    rendered = render_action_description(
        "Refresh data for account {account_id}.",
        {},
    )
    assert "{account_id}" in rendered


async def test_require_write_consent_renders_kwargs_in_prompt(
    writable_env: None, ctx_factory: Callable[..., MagicMock]
) -> None:
    from nz_akahu_mcp.safety import require_write_consent

    @require_write_consent("Refresh account {account_id}.")
    async def my_tool(*, ctx: Any, account_id: str) -> str:
        return f"refreshed-{account_id}"

    ctx = ctx_factory(elicit_action="accept")
    result = await my_tool(ctx=ctx, account_id="acc_xyz")
    assert result == "refreshed-acc_xyz"
    msg = ctx.elicit.await_args[0][0]
    assert "acc_xyz" in msg
