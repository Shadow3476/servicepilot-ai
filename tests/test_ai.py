import json

import pytest

from servicepilot.ai import AIOutputError, AIUnavailable, BedrockTriage, parse_triage
from servicepilot.config import load_settings

GOOD = {
    "summary": "AC not cooling.",
    "suggested_category": "HVAC",
    "suggested_priority": "High",
    "urgent": False,
    "troubleshooting_steps": ["Check thermostat", "Replace filter"],
    "draft_reply": "Thanks for reaching out.",
}
ENABLED = load_settings(
    {"SERVICEPILOT_AI_ENABLED": "true", "SERVICEPILOT_AI_MODEL_ID": "test-model"}
)


class FakeClient:
    """Stands in for bedrock-runtime. Tests never make live calls."""

    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, 0

    def converse(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def test_parse_valid_output_even_with_surrounding_prose():
    t = parse_triage("Here you go:\n" + json.dumps(GOOD))
    assert t.suggested_priority == "High" and len(t.troubleshooting_steps) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        {"suggested_category": "Roofing"},
        {"suggested_priority": "Critical"},
        {"urgent": "yes"},
        {"summary": ""},
        {"troubleshooting_steps": "do stuff"},
        {"troubleshooting_steps": [1, 2]},
    ],
)
def test_schema_violations_rejected(mutation):
    with pytest.raises(AIOutputError):
        parse_triage(json.dumps({**GOOD, **mutation}))


@pytest.mark.parametrize("text", ["", "no json here", "{broken", "[1, 2]"])
def test_non_json_rejected(text):
    with pytest.raises(AIOutputError):
        parse_triage(text)


def test_long_fields_are_truncated():
    t = parse_triage(json.dumps({**GOOD, "summary": "x" * 5000}))
    assert len(t.summary) == 300


def test_disabled_by_default():
    with pytest.raises(AIUnavailable):
        BedrockTriage(load_settings({}))


def test_enabled_without_model_id_is_unavailable():
    with pytest.raises(AIUnavailable):
        BedrockTriage(load_settings({"SERVICEPILOT_AI_ENABLED": "true"}))


def test_triage_happy_path_uses_injected_client():
    client = FakeClient(json.dumps(GOOD))
    result = BedrockTriage(ENABLED, client=client).triage(
        {"service_type": "HVAC", "priority": "Low", "description": "AC broken"}
    )
    assert result.summary == "AC not cooling." and client.calls == 1


def test_client_failure_becomes_unavailable_without_leaking_details():
    client = FakeClient(error=RuntimeError("AccessDenied arn:aws:iam::123:role/x"))
    with pytest.raises(AIUnavailable) as exc:
        BedrockTriage(ENABLED, client=client).triage({"description": "x"})
    assert "arn:" not in str(exc.value)


def test_bad_model_output_raises_output_error():
    with pytest.raises(AIOutputError):
        BedrockTriage(ENABLED, client=FakeClient("sorry, I cannot")).triage(
            {"description": "x"}
        )
