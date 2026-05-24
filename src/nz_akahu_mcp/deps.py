"""Per-process AkahuClient cache.

Tools call `get_client()` to obtain a shared async HTTP client. The first call
constructs it; subsequent calls reuse the same instance.
"""

from __future__ import annotations

from nz_akahu_mcp.client import AkahuClient
from nz_akahu_mcp.config import AkahuConfig

_client: AkahuClient | None = None


def get_client() -> AkahuClient:
    """Return the process-wide AkahuClient, constructing on first use."""
    global _client
    if _client is None:
        _client = AkahuClient(AkahuConfig())
    return _client


async def aclose_client() -> None:
    """Tear down the shared client. Called from the server lifespan."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
