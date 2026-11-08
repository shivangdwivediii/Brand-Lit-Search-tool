"""Credentials come from server-side environment or Streamlit secrets only."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    serpapi_key: str = field(default="", repr=False)
    openai_key: str = field(default="", repr=False)
    model: str = "gpt-4o-mini"

    @property
    def ready(self) -> bool:
        return bool(self.serpapi_key and self.openai_key)


def load_settings(secrets: Mapping | None = None) -> Settings:
    secrets = secrets if secrets is not None else {}

    def get(key: str, fallback: str = "") -> str:
        return str(os.environ.get(key) or secrets.get(key, fallback)).strip()

    return Settings(
        get("SERPAPI_API_KEY"), get("OPENAI_API_KEY"), get("OPENAI_MODEL", "gpt-4o-mini")
    )
