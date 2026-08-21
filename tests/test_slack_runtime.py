from __future__ import annotations

import logging
from pathlib import Path

from slack_video_assistant.config import SlackSettings
from slack_video_assistant.slack_runtime import build_slack_runtime


class FakeApp:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def event(self, name: str):
        def _register(handler):
            self.handlers[name] = handler
            return handler

        return _register


def test_build_slack_runtime_passes_environment_settings_and_logger_to_factories() -> None:
    settings = SlackSettings(
        bot_token="xoxb-test-token",
        app_token="xapp-test-token",
        log_level="INFO",
    )
    logger = logging.getLogger("tests.slack_runtime")
    app = FakeApp()
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
    assert sorted(app.handlers) == ["file_shared", "message"]
    assert calls == {
        "app_token": "xoxb-test-token",
        "app_logger": logger,
        "handler_app": app,
        "handler_token": "xapp-test-token",
        "handler_logger": logger,
    }




def test_build_slack_runtime_creates_missing_video_temp_dir(tmp_path: Path) -> None:
    temp_root = tmp_path / 'runtime-temp-root'
    settings = SlackSettings(
        bot_token='xoxb-test-token',
        app_token='xapp-test-token',
        log_level='INFO',
        video_temp_dir=temp_root,
    )
    logger = logging.getLogger('tests.slack_runtime.temp_root')

    runtime = build_slack_runtime(
        settings,
        logger=logger,
        app_factory=lambda *, token, logger: FakeApp(),
        handler_factory=lambda received_app, app_token, *, logger: object(),
    )

    assert temp_root.exists() is True
    assert temp_root.is_dir() is True
    assert runtime.app is not None


def test_build_slack_runtime_registers_file_shared_and_message_handlers() -> None:
    settings = SlackSettings(
        bot_token="xoxb-test-token",
        app_token="xapp-test-token",
        log_level="INFO",
    )
    logger = logging.getLogger("tests.slack_runtime.handlers")
    registered: dict[str, object] = {}

    class RecordingApp(FakeApp):
        def event(self, name: str):
            def _register(handler):
                registered[name] = handler
                return handler

            return _register

    def app_factory(*, token: str, logger: logging.Logger) -> object:
        assert token == "xoxb-test-token"
        assert logger.name == "tests.slack_runtime.handlers"
        return RecordingApp()

    def handler_factory(received_app: object, app_token: str, *, logger: logging.Logger) -> object:
        assert isinstance(received_app, RecordingApp)
        assert app_token == "xapp-test-token"
        assert logger.name == "tests.slack_runtime.handlers"
        return object()

    runtime = build_slack_runtime(
        settings,
        logger=logger,
        app_factory=app_factory,
        handler_factory=handler_factory,
    )

    assert sorted(registered) == ["file_shared", "message"]
    assert runtime.app is not None
