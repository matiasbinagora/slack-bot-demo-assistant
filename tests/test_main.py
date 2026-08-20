from __future__ import annotations

import logging
import threading

from slack_video_assistant.config import SlackSettings
from slack_video_assistant.main import run
from slack_video_assistant.slack_runtime import SlackRuntime


def make_test_logger() -> logging.Logger:
    logger = logging.getLogger("slack_video_assistant")
    logger.handlers.clear()
    logger.propagate = True
    return logger


class FakeHandler:
    def __init__(self, *, connect_error: Exception | None = None, stop_event: threading.Event | None = None) -> None:
        self.connect_error = connect_error
        self.stop_event = stop_event
        self.connected = False
        self.closed = False
        self.disconnected = False

    def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True
        if self.stop_event is not None:
            self.stop_event.set()

    def close(self) -> None:
        self.closed = True

    def disconnect(self) -> None:
        self.disconnected = True


class FakeRuntimeBuilder:
    def __init__(self, handler: FakeHandler) -> None:
        self.handler = handler
        self.settings: SlackSettings | None = None
        self.logger: logging.Logger | None = None

    def __call__(self, settings: SlackSettings, *, logger: logging.Logger) -> SlackRuntime:
        self.settings = settings
        self.logger = logger
        return SlackRuntime(app=object(), handler=self.handler)


def test_run_constructs_runtime_from_environment_and_starts_lifecycle(caplog) -> None:
    stop_event = threading.Event()
    handler = FakeHandler(stop_event=stop_event)
    builder = FakeRuntimeBuilder(handler)

    with caplog.at_level(logging.INFO, logger="slack_video_assistant"):
        result = run(
            env={
                "SLACK_BOT_TOKEN": "xoxb-test-token",
                "SLACK_APP_TOKEN": "xapp-test-token",
            },
            stop_event=stop_event,
            logger=make_test_logger(),
            runtime_builder=builder,
        )

    assert result == 0
    assert builder.settings is not None
    assert builder.settings.bot_token == "xoxb-test-token"
    assert builder.settings.app_token == "xapp-test-token"
    assert handler.connected is True
    assert handler.closed is True
    assert "connection established" in caplog.text
    assert "stopped" in caplog.text


def test_run_logs_redacted_startup_failure_without_readiness_claim(caplog) -> None:
    stop_event = threading.Event()
    handler = FakeHandler(
        connect_error=RuntimeError(
            "failed to reach wss://slack.example/socket with xapp-secret-token"
        )
    )
    builder = FakeRuntimeBuilder(handler)

    with caplog.at_level(logging.ERROR, logger="slack_video_assistant"):
        result = run(
            env={
                "SLACK_BOT_TOKEN": "xoxb-test-token",
                "SLACK_APP_TOKEN": "xapp-secret-token",
            },
            stop_event=stop_event,
            logger=make_test_logger(),
            runtime_builder=builder,
        )

    assert result == 1
    assert handler.closed is False
    assert "startup failed" in caplog.text
    assert "connection established" not in caplog.text
    assert "xapp-secret-token" not in caplog.text
    assert "wss://slack.example/socket" not in caplog.text
    assert "[REDACTED_TOKEN]" in caplog.text
    assert "[REDACTED_URL]" in caplog.text


def test_run_returns_safe_error_for_missing_credentials(caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="slack_video_assistant"):
        result = run(env={}, logger=make_test_logger())

    assert result == 2
    assert "SLACK_BOT_TOKEN" in caplog.text
    assert "SLACK_APP_TOKEN" in caplog.text
    assert "xoxb" not in caplog.text
    assert "xapp" not in caplog.text


def test_run_handles_clean_shutdown_when_stop_event_is_set_after_start(caplog) -> None:
    stop_event = threading.Event()
    handler = FakeHandler()
    builder = FakeRuntimeBuilder(handler)

    def _set_stop() -> None:
        stop_event.set()

    timer = threading.Timer(0.01, _set_stop)
    timer.start()

    with caplog.at_level(logging.INFO, logger="slack_video_assistant"):
        result = run(
            env={
                "SLACK_BOT_TOKEN": "xoxb-test-token",
                "SLACK_APP_TOKEN": "xapp-test-token",
            },
            stop_event=stop_event,
            logger=make_test_logger(),
            runtime_builder=builder,
        )

    timer.cancel()

    assert result == 0
    assert handler.connected is True
    assert handler.closed is True
    assert "stopped" in caplog.text
