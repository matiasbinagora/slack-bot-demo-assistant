from __future__ import annotations

import signal
import threading
from logging import Logger
from os import environ
from typing import Callable, Mapping

from slack_video_assistant.config import ConfigError, SlackSettings
from slack_video_assistant.logging_utils import configure_logging, redact_sensitive
from slack_video_assistant.slack_runtime import SlackRuntime, build_slack_runtime


class SlackSocketModeRunner:
    def __init__(self, runtime: SlackRuntime, logger: Logger) -> None:
        self._runtime = runtime
        self._logger = logger
        self.ready = False

    def start(self) -> None:
        self._runtime.handler.connect()
        self.ready = True
        self._logger.info("Slack Socket Mode connection established")

    def stop(self) -> None:
        for method_name in ("close", "disconnect"):
            method = getattr(self._runtime.handler, method_name, None)
            if callable(method):
                method()
                break
        self.ready = False
        self._logger.info("Slack Socket Mode stopped")


def install_signal_handlers(
    stop_event: threading.Event,
    logger: Logger,
) -> dict[int, Callable[..., object]]:
    previous_handlers: dict[int, Callable[..., object]] = {}

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received shutdown signal %s", signum)
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, _handle_signal)

    return previous_handlers


def restore_signal_handlers(previous_handlers: Mapping[int, Callable[..., object]]) -> None:
    for signum, previous in previous_handlers.items():
        signal.signal(signum, previous)


def run(
    *,
    env: Mapping[str, str] | None = None,
    stop_event: threading.Event | None = None,
    logger: Logger | None = None,
    runtime_builder: Callable[..., SlackRuntime] = build_slack_runtime,
) -> int:
    stop_event = stop_event or threading.Event()
    settings_env = env if env is not None else environ

    try:
        settings = SlackSettings.from_env(settings_env)
    except ConfigError as exc:
        active_logger = logger or configure_logging(settings_env.get("LOG_LEVEL", "INFO"))
        active_logger.error(str(exc))
        return 2

    active_logger = logger or configure_logging(settings.log_level)

    try:
        runtime = runtime_builder(settings, logger=active_logger)
    except Exception as exc:  # pragma: no cover
        active_logger.error("Slack runtime construction failed: %s", redact_sensitive(exc))
        return 1

    runner = SlackSocketModeRunner(runtime, active_logger)
    previous_handlers = install_signal_handlers(stop_event, active_logger)

    try:
        try:
            runner.start()
        except Exception as exc:
            active_logger.error("Slack Socket Mode startup failed: %s", redact_sensitive(exc))
            return 1

        stop_event.wait()
        return 0
    finally:
        if runner.ready:
            runner.stop()
        restore_signal_handlers(previous_handlers)


def main() -> int:
    return run()
