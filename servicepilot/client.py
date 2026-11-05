"""Client for the public ticket-creation API (API Gateway)."""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

import requests


class ApiError(Exception):
    """Raised with a message that is safe to show to end users."""


def fingerprint(payload: Mapping[str, str]) -> str:
    """Stable hash of a ticket payload, used to spot accidental re-submits."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def submit_ticket(api_url: str, payload: Mapping[str, str], timeout: float = 10) -> str:
    """POST a validated payload and return the new ticket id."""
    try:
        response = requests.post(api_url, json=dict(payload), timeout=timeout)
    except requests.exceptions.Timeout as err:
        raise ApiError("The service took too long to respond. Please try again.") from err
    except requests.exceptions.RequestException as err:
        raise ApiError("Could not reach the ticket service. Please try again later.") from err

    if response.status_code != 201:
        raise ApiError(
            f"The ticket service rejected the request (status {response.status_code})."
        )
    try:
        ticket_id = response.json()["ticket_id"]
    except (ValueError, KeyError, TypeError) as err:
        raise ApiError("The ticket service returned an unexpected response.") from err
    return str(ticket_id)
