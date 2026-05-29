"""Tests for the root server: composition, namespaces, startup banner."""

from __future__ import annotations

import logging

import pytest


async def test_root_server_exposes_all_14_tools(fake_env: None) -> None:
    from nz_akahu_mcp.server import build_server

    mcp = build_server()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        # accounts (6)
        "acct_list_accounts",
        "acct_get_account",
        "acct_get_account_balance",
        "acct_get_pending_transactions",
        "acct_refresh_all_accounts",
        "acct_refresh_account",
        # transactions (6)
        "txn_get_transactions",
        "txn_get_transaction",
        "txn_get_transactions_by_ids",
        "txn_get_pending_transactions",
        "txn_search_transactions",
        "txn_report_transaction_issue",
        # identity (2) -- /categories, /parties, /identity/{id}/verify-name are app-scoped
        "id_get_me",
        "id_verify_name",
    }
    assert names == expected


async def test_composed_plugin_names_fit_kiro_limit(fake_env: None) -> None:
    """Guard: marketplace-plugin-composed names must stay within Kiro's 64-char cap."""
    from nz_akahu_mcp.server import build_server

    mcp = build_server()
    tools = await mcp.list_tools()
    prefix = "mcp__plugin_nz-akahu-mcp_akahu__"
    for t in tools:
        composed = prefix + t.name
        assert len(composed) <= 64, f"{composed} is {len(composed)} chars"


def test_startup_banner_when_bypass_off(
    writable_env: None, caplog: pytest.LogCaptureFixture
) -> None:
    from nz_akahu_mcp.server import log_startup_banner

    with caplog.at_level(logging.INFO, logger="nz_akahu_mcp.server"):
        log_startup_banner()
    blob = "\n".join(r.message for r in caplog.records)
    assert "all writes require confirmation" in blob.lower()


def test_startup_banner_when_bypass_on(
    bypass_env: None, caplog: pytest.LogCaptureFixture
) -> None:
    from nz_akahu_mcp.server import log_startup_banner

    with caplog.at_level(logging.WARNING, logger="nz_akahu_mcp.server"):
        log_startup_banner()
    blob = "\n".join(r.message for r in caplog.records)
    assert "automation bypass enabled" in blob.lower()
    assert "refresh_all_accounts" in blob
    assert "refresh_account" in blob


def test_startup_banner_when_readonly(
    fake_env: None, caplog: pytest.LogCaptureFixture
) -> None:
    from nz_akahu_mcp.server import log_startup_banner

    with caplog.at_level(logging.INFO, logger="nz_akahu_mcp.server"):
        log_startup_banner()
    blob = "\n".join(r.message for r in caplog.records)
    assert "read-only" in blob.lower()


def test_main_constructs_and_runs(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() must build the server and call .run(); we verify the call site."""
    from nz_akahu_mcp import server

    called: dict[str, bool] = {"run": False}

    def fake_run(self: object) -> None:
        called["run"] = True

    monkeypatch.setattr(server.FastMCP, "run", fake_run)
    server.main()
    assert called["run"] is True
