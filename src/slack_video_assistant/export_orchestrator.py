from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Protocol

from slack_video_assistant.logging_utils import redact_sensitive
from slack_video_assistant.media_pipeline import (
    MediaExtractionError,
    MediaProbeError,
    MediaValidationError,
    MediaWorkspace,
    export_video,
    probe_video,
    validate_exported_video,
    write_bounded_stream_to_path,
)
from slack_video_assistant.session_store import ExportRequest
from slack_video_assistant.slack_file_adapter import SlackAdapterError, SlackFileAdapter


class BackgroundExecutor(Protocol):
    def submit(self, job: Callable[[], None]) -> None: ...


class LocalThreadExecutor:
    def submit(self, job: Callable[[], None]) -> None:
        threading.Thread(target=job, daemon=True).start()


class ImmediateExecutor:
    def submit(self, job: Callable[[], None]) -> None:
        job()


class ExportOrchestrator:
    def __init__(
        self,
        *,
        file_adapter_factory: Callable[[Any], SlackFileAdapter],
        executor: BackgroundExecutor | None = None,
        logger: logging.Logger | None = None,
        temp_root: Path | None = None,
        max_video_bytes: int = 104857600,
        max_video_duration_seconds: float = 300.0,
        ffmpeg_command: str = "ffmpeg",
        ffprobe_command: str = "ffprobe",
    ) -> None:
        self._file_adapter_factory = file_adapter_factory
        self._executor = executor or LocalThreadExecutor()
        self._logger = logger or logging.getLogger("slack_video_assistant")
        self._temp_root = temp_root
        self._max_video_bytes = max_video_bytes
        self._max_video_duration_seconds = max_video_duration_seconds
        self._ffmpeg_command = ffmpeg_command
        self._ffprobe_command = ffprobe_command

    def submit(self, *, client: Any, request: ExportRequest) -> None:
        self._executor.submit(lambda: self._run(client=client, request=request))

    def _run(self, *, client: Any, request: ExportRequest) -> None:
        workspace = None
        terminal_state = "failure"
        try:
            adapter = self._file_adapter_factory(client)
            file_record = adapter.get_file_record(request.file_id)
            workspace = MediaWorkspace.create(
                temp_root=self._temp_root,
                request_id=f"{request.key.team_id}-{request.key.channel_id}-{request.key.thread_ts}-export",
            )
            source_path = workspace.source_path
            write_bounded_stream_to_path(
                byte_stream=adapter.iter_download_bytes(file_record),
                destination=source_path,
                max_bytes=self._max_video_bytes,
            )
            probe_video(
                source_path,
                ffprobe_command=self._ffprobe_command,
                max_duration_seconds=self._max_video_duration_seconds,
            )
            exported = export_video(
                source_path=source_path,
                workspace=workspace,
                target_ratio=request.target_ratio,
                ffprobe_command=self._ffprobe_command,
                ffmpeg_command=self._ffmpeg_command,
            )
            validate_exported_video(
                exported.output_path,
                target_ratio=exported.target_ratio,
                expected_width=exported.expected_width,
                expected_height=exported.expected_height,
                ffprobe_command=self._ffprobe_command,
            )
            self._upload_export(client=client, request=request, export_path=exported.output_path)
            terminal_state = "success"
        except _SlackPublishError:
            terminal_state = "publish_failure"
            self._post_message(
                client,
                channel=request.key.channel_id,
                thread_ts=request.key.thread_ts,
                text="I couldn't publish the validated export in Slack, so no file was posted. Please try again in this thread.",
            )
        except Exception as exc:
            self._post_message(
                client,
                channel=request.key.channel_id,
                thread_ts=request.key.thread_ts,
                text=failure_message_for_exception(exc),
            )
        finally:
            if workspace is not None:
                workspace.cleanup(state=terminal_state, logger=self._logger)

    def _upload_export(self, *, client: Any, request: ExportRequest, export_path: Path) -> None:
        try:
            client.files_upload_v2(
                channel=request.key.channel_id,
                thread_ts=request.key.thread_ts,
                file=str(export_path),
                filename=f"export-{request.target_ratio.replace(':', 'x')}.mp4",
                title=f"Validated {request.target_ratio} centered-crop H.264/AAC export",
            )
        except Exception as exc:
            self._logger.error("Slack export publish failed: %s", redact_sensitive(exc))
            raise _SlackPublishError() from exc

    def _post_message(self, client: Any, *, channel: str, thread_ts: str, text: str) -> None:
        try:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
        except Exception as exc:
            self._logger.error("Slack export status publish failed: %s", redact_sensitive(exc))


class _SlackPublishError(RuntimeError):
    """Raised when a validated export cannot be published to Slack."""


def failure_message_for_exception(exc: Exception) -> str:
    if isinstance(exc, SlackAdapterError):
        return "I couldn't download this Slack upload safely. Please try again from this thread."
    if isinstance(exc, MediaValidationError):
        return str(exc)
    if isinstance(exc, MediaProbeError):
        return "I couldn't validate the exported MP4 safely with FFprobe, so no file was published."
    if isinstance(exc, MediaExtractionError):
        return "I couldn't generate the export safely with FFmpeg, so no file was published."
    return "I couldn't complete this export safely. Please try again in this thread."
