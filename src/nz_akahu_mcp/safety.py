"""Safety layer: read-only refusal, write-consent elicitation, automation bypass.

Three layers protect write operations:
  1. AKAHU_READ_ONLY=true (default) -> raise ReadOnlyError before any HTTP call.
  2. ctx.elicit() per call -> raise ElicitationDeclinedError on Decline/Cancel.
  3. automation_bypass + automatable=True opts out of (2) for a small subset.

The bypass is tracked in a module-level registry so the startup banner can
list eligible tools without re-introspecting tool modules.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import AcceptedElicitation

from nz_akahu_mcp.config import AkahuConfig

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

_BYPASS_REGISTRY: set[str] = set()


class MissingCredentialsError(ToolError):
    """Raised when AKAHU_APP_TOKEN or AKAHU_USER_TOKEN is unset."""


class ReadOnlyError(ToolError):
    """Raised when a write tool is invoked while AKAHU_READ_ONLY=true."""


class ElicitationDeclinedError(ToolError):
    """Raised when the user declines or cancels a write elicitation."""


def render_action_description(template: str, kwargs: dict[str, Any]) -> str:
    """Render `{placeholders}` from the tool call's kwargs.

    Missing keys are left as literal `{name}` rather than raising, so a typo
    in the template never breaks a real call. Extras are ignored.
    """

    class _Tolerant(dict[str, Any]):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(_Tolerant(kwargs))


async def confirm_write(ctx: Any, action_description: str) -> None:
    """Ask the user to confirm a write. Raise on decline/cancel."""
    message = f"Confirm: {action_description}"
    result = await ctx.elicit(message, response_type=None)
    if not isinstance(result, AcceptedElicitation):
        raise ElicitationDeclinedError(
            f"User declined or cancelled: {action_description}"
        )


def require_write_consent(
    action_description: str,
    *,
    automatable: bool = False,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator gating a write tool with the three safety layers.

    action_description may contain `{placeholders}` filled from the tool's kwargs
    (e.g. "Refresh account {account_id}.").

    automatable=True marks the tool as bypass-eligible. Must satisfy ALL four
    criteria: idempotent or rate-limited; no third-party side effects;
    easily reversed or self-corrects; common automation use case. Justify
    inline with a comment when adding it to a tool.
    """

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        if automatable:
            _BYPASS_REGISTRY.add(fn.__name__)

        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cfg = AkahuConfig()
            if cfg.read_only:
                raise ReadOnlyError(
                    "Write operations are disabled. To enable: set "
                    "AKAHU_READ_ONLY=false in your .env and restart the MCP "
                    "server. Each write will require your explicit confirmation "
                    "through Claude (or set AKAHU_AUTOMATION_BYPASS=true for "
                    "the automatable subset only)."
                )

            ctx = kwargs.get("ctx")
            rendered = render_action_description(action_description, dict(kwargs))

            if automatable and cfg.automation_bypass:
                logger.info("[BYPASS] %s: %s", fn.__name__, rendered)
            else:
                if ctx is None:  # pragma: no cover  # why: ctx is always injected by FastMCP
                    raise ToolError("Internal error: write tool missing ctx parameter.")
                await confirm_write(ctx, rendered)

            return await fn(*args, **kwargs)

        return wrapper

    return decorator


def bypass_eligible_tools() -> list[str]:
    """Names of tools whose decorator declared automatable=True."""
    return sorted(_BYPASS_REGISTRY)
