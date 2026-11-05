"""Pure functions for dashboard statistics, filtering, sorting, paging."""
from __future__ import annotations

import math
from typing import Iterable

from .models import PRIORITIES, SERVICE_TYPES, STATUSES

SORT_OPTIONS = {
    "Newest first": ("created_at", True),
    "Oldest first": ("created_at", False),
    "Recently updated": ("updated_at", True),
    "Priority (high to low)": ("priority", True),
    "Priority (low to high)": ("priority", False),
}


def compute_stats(tickets: Iterable[dict]) -> dict:
    tickets = list(tickets)
    return {
        "total": len(tickets),
        "by_status": {s: sum(t["status"] == s for t in tickets) for s in STATUSES},
        "by_priority": {p: sum(t["priority"] == p for t in tickets) for p in PRIORITIES},
        "by_service": {
            s: sum(t["service_type"] == s for t in tickets) for s in SERVICE_TYPES
        },
        "urgent_open": sum(
            t["priority"] in ("High", "Emergency") and t["status"] != "Resolved"
            for t in tickets
        ),
    }


def filter_tickets(
    tickets: Iterable[dict],
    *,
    status: str = "All",
    priority: str = "All",
    service: str = "All",
    query: str = "",
) -> list[dict]:
    q = query.strip().lower()
    out = []
    for t in tickets:
        if status != "All" and t["status"] != status:
            continue
        if priority != "All" and t["priority"] != priority:
            continue
        if service != "All" and t["service_type"] != service:
            continue
        haystack = " ".join(
            (t["ticket_id"], t["customer_name"], t["email"], t["description"])
        ).lower()
        if q and q not in haystack:
            continue
        out.append(t)
    return out


def sort_tickets(tickets: Iterable[dict], option: str = "Newest first") -> list[dict]:
    field, reverse = SORT_OPTIONS.get(option, SORT_OPTIONS["Newest first"])
    if field == "priority":
        return sorted(
            tickets, key=lambda t: PRIORITIES.index(t["priority"]), reverse=reverse
        )
    return sorted(tickets, key=lambda t: t.get(field, ""), reverse=reverse)


def paginate(items: list, page: int, page_size: int) -> tuple[list, int, int]:
    """Return (page_items, current_page, total_pages); page is clamped."""
    page_size = max(1, page_size)
    total_pages = max(1, math.ceil(len(items) / page_size))
    page = min(max(1, page), total_pages)
    start = (page - 1) * page_size
    return items[start : start + page_size], page, total_pages
