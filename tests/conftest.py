"""Shared fixtures: env, respx router, Akahu client, Context mock."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import respx

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture by stem (without .json)."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set known-good Akahu env vars for the duration of a test."""
    monkeypatch.setenv("AKAHU_APP_TOKEN", "app_token_test")
    monkeypatch.setenv("AKAHU_USER_TOKEN", "user_token_test")
    monkeypatch.setenv("AKAHU_BASE_URL", "https://api.akahu.io/v1")
    monkeypatch.setenv("AKAHU_READ_ONLY", "true")
    monkeypatch.setenv("AKAHU_AUTOMATION_BYPASS", "false")
    monkeypatch.setenv("AKAHU_REQUEST_TIMEOUT", "5")
    monkeypatch.setenv("AKAHU_LOG_LEVEL", "INFO")


@pytest.fixture
def writable_env(monkeypatch: pytest.MonkeyPatch, fake_env: None) -> None:
    """fake_env plus writes enabled, bypass off (every write elicits)."""
    monkeypatch.setenv("AKAHU_READ_ONLY", "false")
    monkeypatch.setenv("AKAHU_AUTOMATION_BYPASS", "false")


@pytest.fixture
def bypass_env(monkeypatch: pytest.MonkeyPatch, fake_env: None) -> None:
    """fake_env plus writes enabled, bypass on (automatable writes skip elicit)."""
    monkeypatch.setenv("AKAHU_READ_ONLY", "false")
    monkeypatch.setenv("AKAHU_AUTOMATION_BYPASS", "true")


@pytest.fixture
def respx_mock() -> Iterator[respx.MockRouter]:
    """Intercept all httpx traffic for the Akahu base URL."""
    with respx.mock(base_url="https://api.akahu.io/v1", assert_all_called=False) as router:
        yield router


@pytest_asyncio.fixture
async def akahu_client(fake_env: None) -> AsyncIterator[Any]:
    """Construct a fresh AkahuClient and close it after the test."""
    from nz_akahu_mcp.client import AkahuClient
    from nz_akahu_mcp.config import AkahuConfig

    client = AkahuClient(AkahuConfig())
    try:
        yield client
    finally:
        await client.aclose()


def make_ctx(
    *,
    elicit_action: str = "accept",
    elicit_data: Any | None = None,
) -> MagicMock:
    """Build a fake FastMCP Context whose elicit() resolves to a chosen outcome.

    elicit_action: "accept" | "decline" | "cancel".
    elicit_data: payload returned with AcceptedElicitation; ignored otherwise.
    """
    from fastmcp.server.elicitation import (
        AcceptedElicitation,
        CancelledElicitation,
        DeclinedElicitation,
    )

    ctx = MagicMock()
    ctx.info = MagicMock()
    ctx.warning = MagicMock()
    ctx.error = MagicMock()

    if elicit_action == "accept":
        result: Any = AcceptedElicitation(data=elicit_data if elicit_data is not None else {})
    elif elicit_action == "decline":
        result = DeclinedElicitation()
    elif elicit_action == "cancel":
        result = CancelledElicitation()
    else:  # pragma: no cover  # why: defensive against test author typos
        raise ValueError(f"unknown elicit_action: {elicit_action}")

    ctx.elicit = AsyncMock(return_value=result)
    return ctx


@pytest.fixture
def ctx_factory() -> Callable[..., MagicMock]:
    """Expose make_ctx through the pytest fixture system."""
    return make_ctx
