from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """Raised when required environment-backed configuration is missing."""


@dataclass(frozen=True)
class SlackSettings:
    bot_token: str
    app_token: str
    log_level: str = "INFO"
    max_video_bytes: int = 104857600
    video_temp_dir: Path | None = None

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
        max_video_bytes_raw = source.get("MAX_VIDEO_BYTES", "104857600").strip() or "104857600"
        try:
            max_video_bytes = int(max_video_bytes_raw)
        except ValueError as exc:
            raise ConfigError("MAX_VIDEO_BYTES must be an integer.") from exc
        if max_video_bytes <= 0:
            raise ConfigError("MAX_VIDEO_BYTES must be greater than zero.")

        video_temp_dir_raw = source.get("VIDEO_TEMP_DIR", "").strip()
        return cls(
            bot_token=source["SLACK_BOT_TOKEN"].strip(),
            app_token=source["SLACK_APP_TOKEN"].strip(),
            log_level=log_level,
            max_video_bytes=max_video_bytes,
            video_temp_dir=Path(video_temp_dir_raw) if video_temp_dir_raw else None,
        )
