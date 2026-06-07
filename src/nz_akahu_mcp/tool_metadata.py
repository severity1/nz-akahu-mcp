"""Shared MCP tool metadata for ChatGPT Apps SDK compatibility."""

from __future__ import annotations

from typing import Any

READ_ONLY_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": True,
}

NON_DESTRUCTIVE_WRITE_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "openWorldHint": False,
}

IDEMPOTENT_WRITE_ANNOTATIONS: dict[str, Any] = {
    **NON_DESTRUCTIVE_WRITE_ANNOTATIONS,
    "idempotentHint": True,
}
