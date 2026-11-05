"""DynamoDB access for tickets (admin side)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from botocore.exceptions import ClientError

from .models import (
    PRIORITIES,
    STATUSES,
    can_transition,
    normalize_status,
    normalize_ticket,
)


class TicketNotFound(Exception):
    pass


class TicketConflict(Exception):
    """The ticket changed (or was deleted) since it was loaded."""


class InvalidTransition(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TicketStore:
    def __init__(self, table):
        self.table = table

    def list_tickets(self) -> list[dict]:
        """All tickets, following scan pagination, normalised."""
        items: list[dict] = []
        kwargs: dict[str, Any] = {}
        while True:
            page = self.table.scan(**kwargs)
            items.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return [normalize_ticket(i) for i in items if i.get("ticket_id")]

    def get(self, ticket_id: str) -> dict:
        item = self.table.get_item(Key={"ticket_id": ticket_id}).get("Item")
        if not item:
            raise TicketNotFound(ticket_id)
        return normalize_ticket(item)

    def update(
        self,
        ticket_id: str,
        *,
        status: str,
        priority: str,
        expected_version: Optional[int],
        actor: str = "admin",
        current_status: Optional[str] = None,
    ) -> None:
        """Change status/priority with optimistic locking and a history entry.

        ``expected_version`` is the ``version`` the caller loaded (None for
        legacy items that predate versioning). If the stored version differs
        the write is rejected instead of silently overwriting.
        """
        if status not in STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if priority not in PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")
        if current_status is not None and not can_transition(current_status, status):
            raise InvalidTransition(f"{current_status} -> {status} is not allowed")

        now = utc_now()
        entry = {
            "at": now,
            "by": actor,
            "status": status,
            "priority": priority,
            "from_status": normalize_status(current_status) if current_status else "",
        }
        values: dict[str, Any] = {
            ":s": status,
            ":p": priority,
            ":now": now,
            ":new_v": (expected_version or 0) + 1,
            ":entry": [entry],
            ":empty": [],
        }
        if expected_version is None:
            version_cond = "attribute_not_exists(#v)"
        else:
            version_cond = "#v = :v"
            values[":v"] = expected_version
        try:
            self.table.update_item(
                Key={"ticket_id": ticket_id},
                UpdateExpression=(
                    "SET #s = :s, priority = :p, updated_at = :now, #v = :new_v, "
                    "history = list_append(if_not_exists(history, :empty), :entry)"
                ),
                ConditionExpression=f"attribute_exists(ticket_id) AND {version_cond}",
                ExpressionAttributeNames={"#s": "status", "#v": "version"},
                ExpressionAttributeValues=values,
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise TicketConflict(ticket_id) from err
            raise

    def delete(self, ticket_id: str) -> None:
        self.table.delete_item(Key={"ticket_id": ticket_id})

    def delete_all(self, ticket_ids: list[str]) -> int:
        with self.table.batch_writer() as batch:
            for tid in ticket_ids:
                batch.delete_item(Key={"ticket_id": tid})
        return len(ticket_ids)
