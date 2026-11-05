"""Headless smoke tests of the Streamlit pages (no browser, no real AWS)."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from servicepilot import client
from servicepilot.auth import hash_password
from tests.conftest import make_item

ROOT = Path(__file__).resolve().parent.parent
ADMIN_PW = "correct horse battery"


@pytest.fixture(autouse=True)
def clear_streamlit_caches():
    st.cache_resource.clear()
    st.cache_data.clear()
    yield
    st.cache_resource.clear()
    st.cache_data.clear()


def customer_app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


def fill_form(at, name="Jane Doe", desc="The kitchen sink is leaking badly."):
    at.text_input[0].set_value(name)
    at.text_area[0].set_value(desc)
    at.button[0].click()
    return at.run()


def test_customer_form_shows_validation_errors():
    at = fill_form(customer_app(), name="", desc="")
    assert len(at.error) == 2


def test_customer_form_submits_once(monkeypatch):
    calls = []

    class Resp:
        status_code = 201

        def json(self):
            return {"ticket_id": "TKT-42"}

    def fake_post(url, json, timeout):
        calls.append(json)
        return Resp()

    monkeypatch.setattr(client.requests, "post", fake_post)
    at = fill_form(customer_app())
    assert not at.exception and len(calls) == 1
    assert any("TKT-42" in m.value for m in at.markdown)

    at.button[0].click()  # identical re-submit in the same session
    at.run()
    assert len(calls) == 1
    assert at.info


def admin_app(with_hash=True):
    at = AppTest.from_file(str(ROOT / "pages" / "admin.py"), default_timeout=30)
    at.secrets["admin"] = (
        {"password_hash": hash_password(ADMIN_PW, iterations=1000)}
        if with_hash
        else {}
    )
    return at.run()


def login(at, password):
    at.text_input[0].set_value(password)
    at.button[0].click()
    return at.run()


def test_admin_requires_login_and_rejects_wrong_password():
    at = login(admin_app(), "wrong")
    assert at.error and "Incorrect" in at.error[0].value
    assert not at.metric


def test_admin_unconfigured_denies_access():
    at = admin_app(with_hash=False)
    assert at.error and not at.metric


def test_admin_dashboard_reads_dynamodb(table):
    table.put_item(Item=make_item("T1", status="Completed"))  # legacy value
    table.put_item(Item=make_item("T2", priority="Emergency"))
    at = login(admin_app(), ADMIN_PW)
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Total"] == "2"
    assert metrics["Resolved"] == "1"  # legacy "Completed" counted correctly
    assert metrics["Open"] == "1"
    assert len(at.expander) >= 2


def test_admin_empty_state(table):
    at = login(admin_app(), ADMIN_PW)
    assert not at.exception
    assert any("No tickets yet" in i.value for i in at.info)


def test_admin_shows_safe_error_when_table_missing(table):
    table.delete()
    at = login(admin_app(), ADMIN_PW)
    assert at.error and "AWS error" in at.error[0].value
