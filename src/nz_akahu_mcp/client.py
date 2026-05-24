"""Async HTTP client for Akahu (https://developers.akahu.nz/docs/personal-apps).

Auth model: two headers on every call.
  - Authorization: Bearer <user_token>
  - X-Akahu-Id: <app_token>

Retries: 3 attempts on 5xx and httpx.TransportError, exponential backoff (1s/2s/4s).
429 honours Retry-After if numeric, otherwise falls back to the default schedule.
Other 4xx surfaces immediately.

Logging: INFO logs "GET /path -> 200" lines; DEBUG logs response bodies. Auth
tokens are never logged.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any, Self

import httpx

from nz_akahu_mcp.config import AkahuConfig
from nz_akahu_mcp.models import (
    Account,
    Me,
    RefreshResult,
    SupportRequest,
    Transaction,
    VerifyNameResult,
)

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_BASE_BACKOFF = 1.0


class AkahuClient:
    """Thin wrapper around httpx.AsyncClient with auth, retry, and parsing."""

    def __init__(self, config: AkahuConfig | None = None) -> None:
        self.config = config or AkahuConfig()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers=self.config.auth_headers,
            timeout=self.config.request_timeout,
        )
        self._closed = False

    async def aclose(self) -> None:
        """Close the underlying httpx client. Safe to call repeatedly."""
        if self._closed:
            return
        await self._client.aclose()
        self._closed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ---------- core request loop ----------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> dict[str, Any]:
        """Send one request with retry/backoff. Returns parsed JSON dict."""
        last_exc: Exception | None = None

        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._client.request(method, path, params=params, json=json)
            except httpx.TransportError as exc:
                last_exc = exc
                logger.warning(
                    "%s %s transport error (%s); attempt %d/%d",
                    method, path, type(exc).__name__, attempt + 1, _MAX_ATTEMPTS,
                )
                await asyncio.sleep(_BASE_BACKOFF * (2**attempt))
                continue

            logger.info("%s %s -> %d", method, path, response.status_code)

            if response.status_code < 400:
                logger.debug("response body: %s", response.text)
                return response.json()  # type: ignore[no-any-return]

            if response.status_code == 429:
                delay = self._retry_after_seconds(response, default=_BASE_BACKOFF * (2**attempt))
                logger.warning("%s %s rate-limited; sleeping %.1fs", method, path, delay)
                await asyncio.sleep(delay)
                continue

            if 500 <= response.status_code < 600 and attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    "%s %s server error %d; attempt %d/%d",
                    method, path, response.status_code, attempt + 1, _MAX_ATTEMPTS,
                )
                await asyncio.sleep(_BASE_BACKOFF * (2**attempt))
                continue

            response.raise_for_status()

        assert last_exc is not None  # noqa: S101
        raise last_exc

    @staticmethod
    def _retry_after_seconds(response: httpx.Response, *, default: float) -> float:
        """Parse Retry-After in seconds. Fall back to `default` if absent or non-numeric."""
        raw = response.headers.get("Retry-After")
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    # ---------- read endpoints ----------

    async def get_me(self) -> Me:
        data = await self._request("GET", "/me")
        return Me.model_validate(data["item"])

    async def list_accounts(self) -> list[Account]:
        data = await self._request("GET", "/accounts")
        return [Account.model_validate(item) for item in data["items"]]

    async def get_account(self, account_id: str) -> Account:
        data = await self._request("GET", f"/accounts/{account_id}")
        return Account.model_validate(data["item"])

    async def get_transactions(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        cursor: str | None = None,
    ) -> list[Transaction]:
        params: dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if cursor:
            params["cursor"] = cursor
        data = await self._request("GET", "/transactions", params=params or None)
        return [Transaction.model_validate(item) for item in data["items"]]

    async def get_transaction(self, transaction_id: str) -> Transaction:
        data = await self._request("GET", f"/transactions/{transaction_id}")
        return Transaction.model_validate(data["item"])

    async def iter_transactions(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> AsyncIterator[Transaction]:
        """Yield transactions across all pages until cursor.next is None."""
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {}
            if start:
                params["start"] = start
            if end:
                params["end"] = end
            if cursor:
                params["cursor"] = cursor
            data = await self._request("GET", "/transactions", params=params or None)
            for item in data["items"]:
                yield Transaction.model_validate(item)
            next_cursor = (data.get("cursor") or {}).get("next")
            if not next_cursor:
                return
            cursor = next_cursor

    async def get_pending_transactions(self) -> list[Transaction]:
        """All pending transactions across the user's connected accounts."""
        data = await self._request("GET", "/transactions/pending")
        return [Transaction.model_validate(item) for item in data["items"]]

    async def get_account_pending_transactions(self, account_id: str) -> list[Transaction]:
        """Pending transactions for one specific account."""
        data = await self._request("GET", f"/accounts/{account_id}/transactions/pending")
        return [Transaction.model_validate(item) for item in data["items"]]

    async def get_account_transactions(
        self,
        account_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
        cursor: str | None = None,
    ) -> tuple[list[Transaction], str | None]:
        """Settled transactions for one account, paged.

        Returns (items, next_cursor). next_cursor is None on the last page.
        """
        params: dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if cursor:
            params["cursor"] = cursor
        data = await self._request(
            "GET", f"/accounts/{account_id}/transactions", params=params or None
        )
        items = [Transaction.model_validate(item) for item in data["items"]]
        next_cursor = (data.get("cursor") or {}).get("next")
        return items, next_cursor

    async def iter_account_transactions(
        self,
        account_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> AsyncIterator[Transaction]:
        """Yield transactions for one account, transparently paginating."""
        cursor: str | None = None
        while True:
            items, cursor = await self.get_account_transactions(
                account_id, start=start, end=end, cursor=cursor
            )
            for item in items:
                yield item
            if not cursor:
                return

    async def get_transactions_by_ids(self, ids: list[str]) -> list[Transaction]:
        """Batch lookup by transaction id.

        Akahu wire shape: POST /transactions/ids with body = JSON array of strings.
        See https://developers.akahu.nz/reference/post_transactions-ids.
        """
        data = await self._request("POST", "/transactions/ids", json=ids)
        return [Transaction.model_validate(item) for item in data["items"]]

    # ---------- write endpoints ----------

    async def refresh_all(self) -> RefreshResult:
        data = await self._request("POST", "/refresh")
        return RefreshResult.model_validate(data)

    async def refresh_one(self, account_id: str) -> RefreshResult:
        data = await self._request("POST", f"/refresh/{account_id}")
        return RefreshResult.model_validate(data)

    async def report_transaction_issue(
        self,
        transaction_id: str,
        *,
        issue_type: str,
        fields: list[str] | None = None,
        comment: str | None = None,
        other_transaction_id: str | None = None,
    ) -> SupportRequest:
        """Submit a support ticket about a transaction.

        Wire shape per https://developers.akahu.nz/reference/post_support-transaction-id:
          path:  /support/{transaction_id}
          body:  {"type": ..., "other_id": ..., "fields": [...], "comment": "..."}
        """
        body: dict[str, Any] = {"type": issue_type}
        if fields:
            body["fields"] = fields
        if comment:
            body["comment"] = comment
        if other_transaction_id:
            body["other_id"] = other_transaction_id
        data = await self._request("POST", f"/support/{transaction_id}", json=body)
        return SupportRequest.model_validate(data)

    async def verify_name(
        self,
        *,
        family_name: str,
        given_name: str | None = None,
        middle_name: str | None = None,
        initials: list[str] | None = None,
        account_id: str | None = None,
    ) -> VerifyNameResult:
        """Ask Akahu to confirm whether the given name matches the account holder.

        Wire shape per https://developers.akahu.nz/reference/post_verify-name :
          path:  /verify/name             (when account_id is None - all sources)
                 /verify/name/{account_id} (scoped to one account)
          body:  required `family_name`; optional `given_name`, `middle_name`,
                 `initials`.

        Requires the relevant Personal-App scope grant; returns 403 without it.
        """
        body: dict[str, Any] = {"family_name": family_name}
        if given_name:
            body["given_name"] = given_name
        if middle_name:
            body["middle_name"] = middle_name
        if initials:
            body["initials"] = initials
        path = "/verify/name" if account_id is None else f"/verify/name/{account_id}"
        data = await self._request("POST", path, json=body)
        return VerifyNameResult.model_validate(data)
