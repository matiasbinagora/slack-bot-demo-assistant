from __future__ import annotations

import logging
import re


_URL_RE = re.compile(r"https?://\S+|wss?://\S+")
_TOKEN_RE = re.compile(r"\b(?:xox[a-z]-|xapp-)[A-Za-z0-9-]+\b")
_ANTHROPIC_KEY_RE = re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b")
_UNIX_PATH_RE = re.compile(r"(?<![A-Za-z0-9])(?:/[^\s'\"):(]+)+")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s'\"):(]+")


def redact_sensitive(value: object) -> str:
    text = "" if value is None else str(value)
    text = _URL_RE.sub("[REDACTED_URL]", text)
    text = _TOKEN_RE.sub("[REDACTED_TOKEN]", text)
    text = _ANTHROPIC_KEY_RE.sub("[REDACTED_TOKEN]", text)
    text = _UNIX_PATH_RE.sub("[REDACTED_PATH]", text)
    return _WINDOWS_PATH_RE.sub("[REDACTED_PATH]", text)


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("slack_video_assistant")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger
