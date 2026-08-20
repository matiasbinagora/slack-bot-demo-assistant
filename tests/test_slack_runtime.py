from __future__ import annotations

import logging

from slack_video_assistant.config import SlackSettings
from slack_video_assistant.slack_runtime import build_slack_runtime


def test_build_slack_runtime_passes_environment_settings_and_logger_to_factories() -> None:
    settings = SlackSettings(
        bot_token="xoxb-test-token",
        app_token="xapp-test-token",
        log_level="INFO",
    )
    logger = logging.getLogger("tests.slack_runtime")
    app = object()
    handler = object()
    calls: dict[str, object] = {}

    def app_factory(*, token: str, logger: logging.Logger) -> object:
        calls["app_token"] = token
        calls["app_logger"] = logger
        return app

    def handler_factory(received_app: object, app_token: str, *, logger: logging.Logger) -> object:
        calls["handler_app"] = received_app
        calls["handler_token"] = app_token
        calls["handler_logger"] = logger
        return handler

    runtime = build_slack_runtime(
        settings,
        logger=logger,
        app_factory=app_factory,
        handler_factory=handler_factory,
    )

    assert runtime.app is app
    assert runtime.handler is handler
    assert calls == {
        "app_token": "xoxb-test-token",
        "app_logger": logger,
        "handler_app": app,
        "handler_token": "xapp-test-token",
        "handler_logger": logger,
    }
