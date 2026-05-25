"""Safety layer: read-only refusal, write-consent elicitation, automation bypass.

Three layers protect write operations:
  1. AKAHU_READ_ONLY=true (default) -> raise ReadOnlyError before any HTTP call.
  2. ctx.elicit() per call -> raise ElicitationDeclinedError on Decline,
     ElicitationCancelledError (a subclass) on Cancel.
  3. automation_bypass + automatable=True opts out of (2) for marked tools.

`bypass_eligible_tools()` returns the names registered with automatable=True.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from pydantic import BaseModel

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
    """Raised when the user declines a write elicitation.

    Also the base class for ElicitationCancelledError, so `except
    ElicitationDeclinedError` catches both decline and cancel outcomes.
    """


class ElicitationCancelledError(ElicitationDeclinedError):
    """Raised when the user cancels (rather than explicitly declines).

    Subclass of ElicitationDeclinedError so binary "did the user consent?"
    handlers keep working while audit/log paths can distinguish the actions.
    """


class _Confirmation(BaseModel):
    """Empty schema for confirmation-only elicitations.

    Replaces the deprecated response_type=None form, which causes some
    clients (e.g. VS Code) to render an empty, non-functional form. With
    this empty model the client shows only the message and accept/
    decline/cancel actions.
    """


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
    result = await ctx.elicit(message, response_type=_Confirmation)
    match result:
        case AcceptedElicitation():
            return
        case DeclinedElicitation():
            raise ElicitationDeclinedError(
                f"User declined: {action_description}"
            )
        case CancelledElicitation():
            raise ElicitationCancelledError(
                f"User cancelled: {action_description}"
            )
        case _:  # pragma: no cover  # why: ctx.elicit return type is exhausted above
            raise AssertionError(
                f"Unexpected elicitation result: {type(result).__name__}"
            )


def require_write_consent(
    action_description: str,
    *,
    automatable: bool = False,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator gating a write tool with the three safety layers.

    action_description may contain `{placeholders}` filled from the tool's kwargs
    (e.g. "Refresh account {account_id}.").

    automatable=True marks the tool as bypass-eligible: when
    AKAHU_AUTOMATION_BYPASS=true, the elicit() prompt is skipped for these
    tools only.
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
                if ctx is None:  # pragma: no cover
                    raise ToolError("Internal error: write tool missing ctx parameter.")
                await confirm_write(ctx, rendered)

            return await fn(*args, **kwargs)

        return wrapper

    return decorator


def bypass_eligible_tools() -> list[str]:
    """Names of tools whose decorator declared automatable=True."""
    return sorted(_BYPASS_REGISTRY)
