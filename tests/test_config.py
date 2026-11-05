from servicepilot.config import (
    DEFAULT_REGION,
    DEFAULT_TABLE,
    boto_session,
    load_settings,
)


def test_defaults_preserve_existing_behaviour():
    s = load_settings({})
    assert s.region == DEFAULT_REGION == "us-west-1"
    assert s.table_name == DEFAULT_TABLE == "ServicePilotTickets"
    assert s.profile is None
    assert s.ai_enabled is False


def test_env_overrides():
    s = load_settings(
        {
            "SERVICEPILOT_AWS_REGION": "us-east-1",
            "SERVICEPILOT_TABLE_NAME": "Other",
            "SERVICEPILOT_AWS_PROFILE": "dev",
            "SERVICEPILOT_AI_ENABLED": "true",
        }
    )
    assert (s.region, s.table_name, s.profile, s.ai_enabled) == (
        "us-east-1",
        "Other",
        "dev",
        True,
    )


def test_session_uses_configured_region():
    # Regression guard: the region must come from settings, not the CLI default.
    session = boto_session(load_settings({"SERVICEPILOT_AWS_REGION": "us-west-1"}))
    assert session.region_name == "us-west-1"


def test_describe_contains_no_secrets():
    text = str(load_settings({}).describe()).lower()
    assert "secret" not in text and "key" not in text
