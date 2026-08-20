from __future__ import annotations

import logging
import re


_URL_RE = re.compile(r"https?://\S+|wss?://\S+")
_TOKEN_RE = re.compile(r"\b(?:xox[a-z]-|xapp-)[A-Za-z0-9-]+\b")


def redact_sensitive(value: object) -> str:
    text = "" if value is None else str(value)
    text = _URL_RE.sub("[REDACTED_URL]", text)
    return _TOKEN_RE.sub("[REDACTED_TOKEN]", text)


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("slack_video_assistant")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger
