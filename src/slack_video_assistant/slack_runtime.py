from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import Any, Callable

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_video_assistant.config import SlackSettings
from slack_video_assistant.explanation_orchestrator import ExplanationOrchestrator
from slack_video_assistant.media_pipeline import _prepare_temp_root
from slack_video_assistant.session_store import ThreadSessionStore
from slack_video_assistant.slack_events import ProcessedEventStore, SlackEventHandler, register_slack_handlers
from slack_video_assistant.slack_file_adapter import SlackFileAdapter


@dataclass
class SlackRuntime:
    app: Any
    handler: Any


class _RequestsLikeSlackDownloader:
    def stream(self, *, url: str, headers: dict[str, str]) -> Any:
        from urllib.request import Request, urlopen

        request = Request(url, headers=headers)
        response = urlopen(request)

        class _ResponseWrapper:
            def __init__(self, raw_response: Any) -> None:
                self._raw_response = raw_response

            def iter_bytes(self, chunk_size: int = 65536):
                while True:
                    chunk = self._raw_response.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        return _ResponseWrapper(response)


def build_slack_runtime(
    settings: SlackSettings,
    *,
    logger: Logger,
    app_factory: Callable[..., Any] = App,
    handler_factory: Callable[..., Any] = SocketModeHandler,
) -> SlackRuntime:
    prepared_temp_root = _prepare_temp_root(settings.video_temp_dir)
    app = app_factory(token=settings.bot_token, logger=logger)

    def _file_adapter_factory(client: Any) -> SlackFileAdapter:
        return SlackFileAdapter(
            bot_token=settings.bot_token,
            client=client,
            downloader=_RequestsLikeSlackDownloader(),
            max_bytes=settings.max_video_bytes,
            temp_root=prepared_temp_root,
        )

    register_slack_handlers(
        app,
        SlackEventHandler(
            file_adapter_factory=_file_adapter_factory,
            session_store=ThreadSessionStore(),
            processed_events=ProcessedEventStore(),
            logger=logger,
            explanation_orchestrator=ExplanationOrchestrator(
                file_adapter_factory=_file_adapter_factory,
                logger=logger,
                temp_root=prepared_temp_root,
                max_video_bytes=settings.max_video_bytes,
                max_video_duration_seconds=settings.max_video_duration_seconds,
            ),
        ),
    )

    handler = handler_factory(app, settings.app_token, logger=logger)
    return SlackRuntime(app=app, handler=handler)
