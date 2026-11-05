from decimal import Decimal

import pytest

from servicepilot.store import (
    InvalidTransition,
    TicketConflict,
    TicketNotFound,
    TicketStore,
)
from tests.conftest import make_item


def test_list_returns_all_tickets_across_scan_pages(table):
    # ~400KB of items forces DynamoDB to paginate a single scan (1MB cap),
    # which is the pagination path the admin panel has to follow.
    big = "x" * 100_000
    for i in range(15):
        table.put_item(Item=make_item(f"T{i:02d}", notes=big))
    store = TicketStore(table)
    assert "LastEvaluatedKey" in table.scan()  # precondition: one page is not enough
    assert len(store.list_tickets()) == 15


def test_list_handles_legacy_and_decimal_items(table):
    table.put_item(Item={"ticket_id": "OLD", "status": "Completed", "n": Decimal("3")})
    (t,) = TicketStore(table).list_tickets()
    assert t["status"] == "Resolved" and t["n"] == 3


def test_get_missing_raises(table):
    with pytest.raises(TicketNotFound):
        TicketStore(table).get("nope")


def test_update_sets_status_history_and_version(table):
    table.put_item(Item=make_item("T1"))
    store = TicketStore(table)
    store.update("T1", status="In Progress", priority="High",
                 expected_version=None, current_status="Open")
    t = store.get("T1")
    assert (t["status"], t["priority"], t["version"]) == ("In Progress", "High", 1)
    assert t["history"][0]["status"] == "In Progress"
    assert t["updated_at"] >= t["created_at"]
    # other fields untouched
    assert t["description"].startswith("Air conditioner")


def test_stale_update_is_rejected(table):
    table.put_item(Item=make_item("T1"))
    store = TicketStore(table)
    store.update("T1", status="In Progress", priority="Medium", expected_version=None)
    with pytest.raises(TicketConflict):  # second admin still holds the old version
        store.update("T1", status="Resolved", priority="Medium", expected_version=None)
    assert store.get("T1")["status"] == "In Progress"


def test_update_missing_ticket_does_not_create_it(table):
    store = TicketStore(table)
    with pytest.raises(TicketConflict):
        store.update("ghost", status="Resolved", priority="Low", expected_version=None)
    assert store.list_tickets() == []


def test_invalid_values_rejected(table):
    table.put_item(Item=make_item("T1"))
    store = TicketStore(table)
    with pytest.raises(ValueError):
        store.update("T1", status="Completed", priority="Low", expected_version=None)
    with pytest.raises(ValueError):
        store.update("T1", status="Open", priority="Nope", expected_version=None)


def test_invalid_transition_blocked_when_current_known(table):
    table.put_item(Item=make_item("T1", status="Resolved"))
    with pytest.raises(InvalidTransition):
        TicketStore(table).update("T1", status="In Progress", priority="Low",
                                  expected_version=None, current_status="Resolved")
    assert TicketStore(table).get("T1")["status"] == "Resolved"


def test_delete_and_delete_all(table):
    for i in range(3):
        table.put_item(Item=make_item(f"T{i}"))
    store = TicketStore(table)
    store.delete("T0")
    assert {t["ticket_id"] for t in store.list_tickets()} == {"T1", "T2"}
    assert store.delete_all(["T1", "T2"]) == 2
    assert store.list_tickets() == []
