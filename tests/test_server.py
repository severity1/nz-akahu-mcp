"""Tests for the root server: composition, namespaces, startup banner."""

from __future__ import annotations

import logging

import pytest


async def test_root_server_exposes_all_23_tools(fake_env: None) -> None:
    from nz_akahu_mcp.server import build_server

    mcp = build_server()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        # accounts (6)
        "accounts_list_accounts",
        "accounts_get_account",
        "accounts_get_account_balance",
        "accounts_get_pending_transactions",
        "accounts_refresh_all_accounts",
        "accounts_refresh_account",
        # transactions (6)
        "transactions_get_transactions",
        "transactions_get_transaction",
        "transactions_get_transactions_by_ids",
        "transactions_get_pending_transactions",
        "transactions_search_transactions",
        "transactions_report_transaction_issue",
        # insights (6)
        "insights_analyse_spending",
        "insights_find_recurring_payments",
        "insights_cash_flow_summary",
        "insights_compare_periods",
        "insights_top_merchants",
        "insights_detect_unusual_transactions",
        # planning (3)
        "planning_project_balance",
        "planning_upcoming_recurring",
        "planning_savings_capacity",
        # identity (2) -- /categories, /parties, /identity/{id}/verify-name are app-scoped
        "identity_get_me",
        "identity_verify_name",
    }
    assert names == expected


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
