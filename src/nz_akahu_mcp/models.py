"""Pydantic shapes for Akahu API responses.

Field aliases handle Akahu's underscore-prefixed ids (`_id`, `_account`, etc.).
All models are `extra="ignore"` so unknown fields in future API versions
don't break parsing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


# ---------- shared envelopes ----------


class Cursor(_Base):
    next: str | None = None


# ---------- accounts ----------


class Connection(_Base):
    id: str = Field(alias="_id")
    name: str
    logo: str | None = None


class Balance(_Base):
    currency: str = "NZD"
    current: float
    available: float | None = None
    limit: float | None = None
    overdrawn: bool | None = None


class Refreshed(_Base):
    balance: datetime | None = None
    meta: datetime | None = None
    transactions: datetime | None = None


class Account(_Base):
    id: str = Field(alias="_id")
    name: str
    status: str
    formatted_account: str | None = None
    type: str
    attributes: list[str] = Field(default_factory=list)
    balance: Balance | None = None
    connection: Connection | None = None
    refreshed: Refreshed | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# ---------- transactions ----------


class Merchant(_Base):
    id: str = Field(alias="_id")
    name: str
    website: str | None = None


class CategoryGroup(_Base):
    id: str = Field(alias="_id")
    name: str


class Category(_Base):
    id: str = Field(alias="_id")
    name: str
    groups: dict[str, CategoryGroup] = Field(default_factory=dict)
    components: list[str] = Field(default_factory=list)


class TransactionMeta(_Base):
    particulars: str | None = None
    code: str | None = None
    reference: str | None = None
    other_account: str | None = None
    conversion: dict[str, Any] | None = None
    card_suffix: str | None = None
    logo: str | None = None


class Transaction(_Base):
    id: str = Field(alias="_id")
    account: str = Field(alias="_account")
    user: str | None = Field(default=None, alias="_user")
    connection: str | None = Field(default=None, alias="_connection")
    date: datetime
    description: str
    amount: float
    balance: float | None = None
    type: str
    hash: str | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None
    merchant: Merchant | None = None
    category: Category | None = None
    meta: TransactionMeta = Field(default_factory=TransactionMeta)


# ---------- identity ----------


class Phone(_Base):
    verified: bool | None = None
    number: str | None = None


class Address(_Base):
    street: str | None = None
    city: str | None = None
    postcode: str | None = None
    country: str | None = None


class Profile(_Base):
    first_name: str | None = None
    last_name: str | None = None
    phone: Phone | None = None
    address: Address | None = None


class Preferences(_Base):
    online_banking: bool | None = None


class Me(_Base):
    id: str = Field(alias="_id")
    email: str | None = None
    access_granted_at: datetime | None = None
    profile: Profile | None = None
    preferences: Preferences | None = None


class Party(_Base):
    id: str = Field(alias="_id")
    account: str | None = Field(default=None, alias="_account")
    type: str
    name: str
    address: str | None = None
    tax_number: str | None = None


# ---------- write results ----------


class RefreshResult(_Base):
    success: bool
    message: str | None = None


class SupportRequest(_Base):
    success: bool
    message: str | None = None


class VerifyNameResult(_Base):
    success: bool
    item: dict[str, Any] | None = None
    message: str | None = None
