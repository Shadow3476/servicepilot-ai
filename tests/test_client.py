import pytest
import requests

from servicepilot import client
from servicepilot.client import ApiError, fingerprint, submit_ticket

PAYLOAD = {"customer_name": "A", "description": "d" * 12}


class Resp:
    def __init__(self, status=201, body=None, bad_json=False):
        self.status_code = status
        self._body = body
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("bad json")
        return self._body


def patch_post(monkeypatch, result):
    def fake(url, json, timeout):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(client.requests, "post", fake)


def test_success_returns_ticket_id(monkeypatch):
    patch_post(monkeypatch, Resp(201, {"ticket_id": "TKT-1"}))
    assert submit_ticket("http://x", PAYLOAD) == "TKT-1"


@pytest.mark.parametrize(
    "result",
    [
        requests.exceptions.ConnectionError("boom: internal-host"),
        requests.exceptions.Timeout(),
        Resp(500, {}),
        Resp(201, {}),
        Resp(201, bad_json=True),
    ],
)
def test_failures_become_safe_api_errors(monkeypatch, result):
    patch_post(monkeypatch, result)
    with pytest.raises(ApiError) as exc:
        submit_ticket("http://x", PAYLOAD)
    assert "internal-host" not in str(exc.value)


def test_fingerprint_is_stable_and_sensitive():
    assert fingerprint({"a": "1", "b": "2"}) == fingerprint({"b": "2", "a": "1"})
    assert fingerprint({"a": "1"}) != fingerprint({"a": "2"})
