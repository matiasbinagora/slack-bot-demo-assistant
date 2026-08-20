from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping


class ConfigError(ValueError):
    """Raised when required environment-backed configuration is missing."""


@dataclass(frozen=True)
class SlackSettings:
    bot_token: str
    app_token: str
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SlackSettings":
        source = env if env is not None else environ
        missing = [
            name
            for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN")
            if not source.get(name, "").strip()
        ]
        if missing:
            joined = ", ".join(missing)
            raise ConfigError(
                f"Missing required environment variable(s): {joined}. "
                "Provide Slack tokens through the process environment only."
            )

        log_level = source.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        return cls(
            bot_token=source["SLACK_BOT_TOKEN"].strip(),
            app_token=source["SLACK_APP_TOKEN"].strip(),
            log_level=log_level,
        )
