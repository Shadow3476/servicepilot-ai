from servicepilot.models import normalize_ticket
from servicepilot.stats import compute_stats, filter_tickets, paginate, sort_tickets


def mk(i, **kw):
    base = {
        "ticket_id": f"T{i}",
        "customer_name": f"Cust {i}",
        "email": f"c{i}@example.com",
        "description": f"problem number {i}",
        "created_at": f"2026-01-0{i}T00:00:00",
    }
    base.update(kw)
    return normalize_ticket(base)


TICKETS = [
    mk(1, status="Open", priority="Low", service_type="HVAC"),
    mk(2, status="In Progress", priority="Emergency", service_type="Plumbing"),
    mk(3, status="Completed", priority="High", service_type="HVAC"),
    mk(4, status="Open", priority="High", service_type="Electrical"),
]


def test_stats_count_actual_records_and_legacy_status():
    s = compute_stats(TICKETS)
    assert s["total"] == 4
    assert s["by_status"] == {"Open": 2, "In Progress": 1, "Resolved": 1}
    assert s["by_priority"]["High"] == 2
    assert s["by_service"]["HVAC"] == 2
    assert s["urgent_open"] == 2  # Emergency(in progress) + High(open); resolved excluded


def test_stats_empty():
    assert compute_stats([])["total"] == 0


def test_filters_combine():
    out = filter_tickets(TICKETS, status="Open", service="Electrical")
    assert [t["ticket_id"] for t in out] == ["T4"]


def test_search_matches_id_name_email_description_case_insensitive():
    assert len(filter_tickets(TICKETS, query="T2")) == 1
    assert len(filter_tickets(TICKETS, query="CUST 3")) == 1
    assert len(filter_tickets(TICKETS, query="c4@EXAMPLE")) == 1
    assert len(filter_tickets(TICKETS, query="number")) == 4
    assert filter_tickets(TICKETS, query="zzz") == []


def test_sorting():
    assert sort_tickets(TICKETS)[0]["ticket_id"] == "T4"
    assert sort_tickets(TICKETS, "Oldest first")[0]["ticket_id"] == "T1"
    assert sort_tickets(TICKETS, "Priority (high to low)")[0]["priority"] == "Emergency"
    assert sort_tickets(TICKETS, "Priority (low to high)")[0]["priority"] == "Low"


def test_pagination_clamps():
    items = list(range(25))
    page, cur, total = paginate(items, 2, 10)
    assert page == list(range(10, 20)) and (cur, total) == (2, 3)
    assert paginate(items, 99, 10)[1] == 3
    assert paginate(items, 0, 10)[1] == 1
    assert paginate([], 1, 10) == ([], 1, 1)
