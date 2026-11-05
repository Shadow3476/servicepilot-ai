import boto3
import pytest
from moto import mock_aws

REGION = "us-west-1"
TABLE = "ServicePilotTickets"


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    """Dummy credentials so no test can ever pick up real ones."""
    for key in ("AWS_PROFILE", "SERVICEPILOT_AWS_PROFILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        tbl = ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "ticket_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "ticket_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield tbl


def make_item(ticket_id, **overrides):
    item = {
        "ticket_id": ticket_id,
        "customer_name": "Jane Doe",
        "email": "jane@example.com",
        "service_type": "HVAC",
        "description": "Air conditioner is not cooling the house.",
        "priority": "Medium",
        "status": "Open",
        "created_at": "2026-01-01T10:00:00+00:00",
    }
    item.update(overrides)
    return item
