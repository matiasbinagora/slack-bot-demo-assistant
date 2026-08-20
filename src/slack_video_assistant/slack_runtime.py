from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import Any, Callable

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_video_assistant.config import SlackSettings


@dataclass
class SlackRuntime:
    app: Any
    handler: Any


def build_slack_runtime(
    settings: SlackSettings,
    *,
    logger: Logger,
    app_factory: Callable[..., Any] = App,
    handler_factory: Callable[..., Any] = SocketModeHandler,
) -> SlackRuntime:
    app = app_factory(token=settings.bot_token, logger=logger)
    handler = handler_factory(app, settings.app_token, logger=logger)
    return SlackRuntime(app=app, handler=handler)
