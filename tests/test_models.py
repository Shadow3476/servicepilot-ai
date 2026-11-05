import pytest

from servicepilot.models import (
    ValidationError,
    can_transition,
    normalize_status,
    normalize_ticket,
    validate_ticket_input,
)

VALID = {
    "customer_name": "  Jane Doe ",
    "email": "jane@example.com",
    "service_type": "Plumbing",
    "priority": "High",
    "description": "The kitchen sink is leaking badly.",
}


def test_valid_input_is_cleaned():
    out = validate_ticket_input(VALID)
    assert out["customer_name"] == "Jane Doe"
    assert out["service_type"] == "Plumbing"


def test_email_is_optional():
    assert validate_ticket_input({**VALID, "email": ""})["email"] == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("customer_name", ""),
        ("customer_name", "x" * 101),
        ("email", "not-an-email"),
        ("service_type", "Roofing"),
        ("priority", "Urgent!!"),
        ("description", ""),
        ("description", "short"),
        ("description", "x" * 2001),
    ],
)
def test_invalid_inputs_rejected(field, value):
    with pytest.raises(ValidationError) as exc:
        validate_ticket_input({**VALID, field: value})
    assert exc.value.errors


def test_control_characters_stripped():
    out = validate_ticket_input({**VALID, "customer_name": "Jane\x00 Doe\x07"})
    assert out["customer_name"] == "Jane Doe"


def test_legacy_completed_maps_to_resolved():
    assert normalize_status("Completed") == "Resolved"
    assert normalize_status(None) == "Open"
    assert normalize_status("garbage") == "Open"


def test_transitions():
    assert can_transition("Open", "In Progress")
    assert can_transition("In Progress", "Resolved")
    assert can_transition("Resolved", "Open")  # reopen
    assert not can_transition("Resolved", "In Progress")
    assert can_transition("Completed", "Resolved")  # legacy, no-op


def test_normalize_legacy_item_fills_defaults():
    t = normalize_ticket({"ticket_id": "T1", "status": "Completed"})
    assert t["status"] == "Resolved"
    assert t["priority"] == "Medium"
    assert t["service_type"] == "Other"
    assert t["history"] == [] and t["version"] is None
