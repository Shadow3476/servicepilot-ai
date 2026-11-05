"""Ticket vocabulary, validation, and normalisation of stored items."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any, Mapping

STATUSES = ("Open", "In Progress", "Resolved")
PRIORITIES = ("Low", "Medium", "High", "Emergency")
SERVICE_TYPES = ("HVAC", "Plumbing", "Electrical", "Appliance", "Other")

# Tickets written before this change used "Completed". They are read as
# "Resolved"; stored values are only rewritten when a ticket is next updated
# (or by scripts/migrate_status.py).
LEGACY_STATUS = {"Completed": "Resolved"}

TRANSITIONS = {
    "Open": {"In Progress", "Resolved"},
    "In Progress": {"Open", "Resolved"},
    "Resolved": {"Open"},  # reopen first; work resumes via Open -> In Progress
}

MAX_NAME = 100
MAX_EMAIL = 254
MIN_DESCRIPTION = 10
MAX_DESCRIPTION = 2000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _clean(value: Any, *, multiline: bool = False) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    keep = {"\n", "\t"} if multiline else set()
    text = "".join(
        ch for ch in text if ch in keep or unicodedata.category(ch)[0] != "C"
    )
    return text.strip()


def validate_ticket_input(data: Mapping[str, Any]) -> dict:
    """Return a cleaned ticket payload or raise ValidationError."""
    errors: list[str] = []
    name = _clean(data.get("customer_name"))
    email = _clean(data.get("email"))
    description = _clean(data.get("description"), multiline=True)
    service = _clean(data.get("service_type"))
    priority = _clean(data.get("priority")) or "Medium"

    if not name:
        errors.append("Please enter your name.")
    elif len(name) > MAX_NAME:
        errors.append(f"Name must be at most {MAX_NAME} characters.")
    if email and (len(email) > MAX_EMAIL or not _EMAIL_RE.match(email)):
        errors.append("Please enter a valid email address.")
    if service not in SERVICE_TYPES:
        errors.append("Please choose a service type.")
    if priority not in PRIORITIES:
        errors.append("Please choose a priority.")
    if not description:
        errors.append("Please describe the problem.")
    elif len(description) < MIN_DESCRIPTION:
        errors.append(
            f"Please give a bit more detail (at least {MIN_DESCRIPTION} characters)."
        )
    elif len(description) > MAX_DESCRIPTION:
        errors.append(f"Description must be at most {MAX_DESCRIPTION} characters.")

    if errors:
        raise ValidationError(errors)
    return {
        "customer_name": name,
        "email": email,
        "service_type": service,
        "priority": priority,
        "description": description,
    }


def normalize_status(status: Any) -> str:
    status = str(status or "Open")
    status = LEGACY_STATUS.get(status, status)
    return status if status in STATUSES else "Open"


def can_transition(current: str, new: str) -> bool:
    current, new = normalize_status(current), normalize_status(new)
    return current == new or new in TRANSITIONS[current]


def _plain(value: Any) -> Any:
    """Convert DynamoDB Decimals (and nested containers) to plain Python."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def normalize_ticket(item: Mapping[str, Any]) -> dict:
    """Make a stored item (possibly legacy / partial) safe for the UI."""
    t = _plain(dict(item))
    t["ticket_id"] = str(t.get("ticket_id", ""))
    t["status"] = normalize_status(t.get("status"))
    if t.get("priority") not in PRIORITIES:
        t["priority"] = "Medium"
    if t.get("service_type") not in SERVICE_TYPES:
        t["service_type"] = "Other"
    for key in ("customer_name", "email", "description", "created_at"):
        t[key] = str(t.get(key) or "")
    t["updated_at"] = str(t.get("updated_at") or t["created_at"])
    t["history"] = t.get("history") if isinstance(t.get("history"), list) else []
    version = t.get("version")
    t["version"] = version if isinstance(version, int) else None
    return t
