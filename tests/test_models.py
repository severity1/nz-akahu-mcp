"""Tests for pydantic models: aliases, ISO coercion, forward compat."""

from __future__ import annotations

from datetime import datetime

from tests.conftest import load_fixture


def test_me_parses_underscore_id() -> None:
    from nz_akahu_mcp.models import Me

    me = Me.model_validate(load_fixture("me")["item"])
    assert me.id == "user_test_001"
    assert me.profile is not None
    assert me.profile.first_name == "Hemi"
    assert me.profile.phone is not None
    assert me.profile.phone.verified is True


def test_account_aliases_and_balance() -> None:
    from nz_akahu_mcp.models import Account

    acc = Account.model_validate(load_fixture("accounts")["items"][0])
    assert acc.id == "acc_chq_001"
    assert acc.balance is not None
    assert acc.balance.current == 2543.21
    assert acc.balance.currency == "NZD"
    assert acc.connection is not None
    assert acc.connection.id == "conn_anz"


def test_transaction_parses_iso_date_and_meta() -> None:
    from nz_akahu_mcp.models import Transaction

    txn = Transaction.model_validate(load_fixture("transactions")["items"][0])
    assert txn.id == "txn_001"
    assert isinstance(txn.date, datetime)
    assert txn.meta.particulars == "COUNTDOWN"
    assert txn.meta.card_suffix == "1234"


def test_transaction_with_no_merchant() -> None:
    """Salary transaction in fixture has no merchant; field should be None."""
    from nz_akahu_mcp.models import Transaction

    txn = Transaction.model_validate(load_fixture("transactions")["items"][2])
    assert txn.id == "txn_003"
    assert txn.merchant is None


def test_category_with_groups() -> None:
    from nz_akahu_mcp.models import Category

    cat = Category.model_validate(load_fixture("categories")["items"][0])
    assert cat.id == "cat_groceries"
    assert "personal_finance" in cat.groups
    assert cat.groups["personal_finance"].name == "Food"


def test_connection_minimal() -> None:
    from nz_akahu_mcp.models import Connection

    conn = Connection.model_validate(load_fixture("connections")["items"][0])
    assert conn.id == "conn_anz"
    assert conn.name == "ANZ"


def test_unknown_fields_are_ignored() -> None:
    """Forward compat: new Akahu fields must not break parsing."""
    from nz_akahu_mcp.models import Account

    payload = {
        **load_fixture("accounts")["items"][0],
        "brand_new_field_from_2027": {"x": 1},
    }
    acc = Account.model_validate(payload)
    assert acc.id == "acc_chq_001"


def test_refresh_result_minimal() -> None:
    from nz_akahu_mcp.models import RefreshResult

    r = RefreshResult.model_validate({"success": True})
    assert r.success is True
    assert r.message is None


def test_support_request_minimal() -> None:
    from nz_akahu_mcp.models import SupportRequest

    r = SupportRequest.model_validate({"success": True})
    assert r.success is True


def test_verify_name_result_parses() -> None:
    from nz_akahu_mcp.models import VerifyNameResult

    r = VerifyNameResult.model_validate({"success": True, "item": {"matched": True}})
    assert r.success is True
    assert r.item == {"matched": True}

    r2 = VerifyNameResult.model_validate({"success": False, "message": "Forbidden"})
    assert r2.success is False
    assert r2.message == "Forbidden"


def test_cursor_null_next() -> None:
    from nz_akahu_mcp.models import Cursor

    assert Cursor.model_validate({"next": None}).next is None
    assert Cursor.model_validate({}).next is None


def test_transaction_meta_defaults_empty() -> None:
    from nz_akahu_mcp.models import TransactionMeta

    m = TransactionMeta.model_validate({})
    assert m.particulars is None
    assert m.conversion is None
