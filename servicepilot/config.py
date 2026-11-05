"""Runtime configuration, read from environment variables.

No credentials live here. AWS credentials come from the standard boto3
credential chain (or the optional named profile).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

import boto3

# Defaults match what the project already used, so existing setups keep working.
DEFAULT_REGION = "us-west-1"
DEFAULT_TABLE = "ServicePilotTickets"
DEFAULT_API_URL = "https://4mps7hcgi7.execute-api.us-west-1.amazonaws.com/tickets"


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    region: str = DEFAULT_REGION
    table_name: str = DEFAULT_TABLE
    profile: Optional[str] = None
    api_url: str = DEFAULT_API_URL
    ai_enabled: bool = False
    ai_model_id: Optional[str] = None
    ai_region: Optional[str] = None

    def describe(self) -> dict:
        """Non-sensitive summary, safe to show in the admin UI."""
        return {
            "region": self.region,
            "table": self.table_name,
            "profile": self.profile or "(default credential chain)",
            "ai": "enabled" if self.ai_enabled else "disabled",
        }


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        region=env.get("SERVICEPILOT_AWS_REGION") or DEFAULT_REGION,
        table_name=env.get("SERVICEPILOT_TABLE_NAME") or DEFAULT_TABLE,
        profile=env.get("SERVICEPILOT_AWS_PROFILE") or None,
        api_url=env.get("SERVICEPILOT_API_URL") or DEFAULT_API_URL,
        ai_enabled=_truthy(env.get("SERVICEPILOT_AI_ENABLED")),
        ai_model_id=env.get("SERVICEPILOT_AI_MODEL_ID") or None,
        ai_region=env.get("SERVICEPILOT_AI_REGION") or None,
    )


def boto_session(settings: Settings) -> boto3.Session:
    """Session pinned to the configured region (and profile, if one is set)."""
    return boto3.Session(
        profile_name=settings.profile, region_name=settings.region
    )
