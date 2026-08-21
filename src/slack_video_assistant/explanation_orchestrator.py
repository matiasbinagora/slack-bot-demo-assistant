from __future__ import annotations

import base64
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from slack_video_assistant.claude_analysis import (
    AnalysisConfigurationError,
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    AnalysisRequest,
    AnalysisResult,
    AnalysisTimeoutError,
    ClaudeAnalyzer,
    FrameEvidence,
    TranscriptEvidence,
    build_claude_analyzer,
)
from slack_video_assistant.logging_utils import redact_sensitive
from slack_video_assistant.media_pipeline import (
    AudioEvidence,
    MediaExtractionError,
    MediaPipelineError,
    MediaProbeError,
    MediaValidationError,
    PreparedMediaEvidence,
    prepare_media_evidence,
)
from slack_video_assistant.session_store import ThreadSession
from slack_video_assistant.slack_file_adapter import SlackAdapterError, SlackFileAdapter


class BackgroundExecutor(Protocol):
    def submit(self, job: Callable[[], None]) -> None: ...


class AnalyzerFactory(Protocol):
    def __call__(self) -> ClaudeAnalyzer: ...


@dataclass(frozen=True)
class ExplanationContext:
    team_id: str
    channel_id: str
    thread_ts: str


class LocalThreadExecutor:
    def submit(self, job: Callable[[], None]) -> None:
        threading.Thread(target=job, daemon=True).start()


class TranscriptionFailureError(RuntimeError):
    pass


class ExplanationOrchestrator:
    def __init__(
        self,
        *,
        file_adapter_factory: Callable[[Any], SlackFileAdapter],
        analyzer_factory: AnalyzerFactory = build_claude_analyzer,
        executor: BackgroundExecutor | None = None,
        logger: logging.Logger | None = None,
        temp_root: Path | None = None,
        max_video_bytes: int = 104857600,
        max_video_duration_seconds: float = 300.0,
        transcriber: Any | None = None,
    ) -> None:
        self._file_adapter_factory = file_adapter_factory
        self._analyzer_factory = analyzer_factory
        self._executor = executor or LocalThreadExecutor()
        self._logger = logger or logging.getLogger("slack_video_assistant")
        self._temp_root = temp_root
        self._max_video_bytes = max_video_bytes
        self._max_video_duration_seconds = max_video_duration_seconds
        self._transcriber = transcriber

    def enqueue(self, *, client: Any, session: ThreadSession) -> None:
        context = ExplanationContext(
            team_id=session.key.team_id,
            channel_id=session.key.channel_id,
            thread_ts=session.key.thread_ts,
        )
        self._executor.submit(lambda: self._run(client=client, context=context, session=session))

    def _run(self, *, client: Any, context: ExplanationContext, session: ThreadSession) -> None:
        workspace = None
        terminal_state = "failure"
        try:
            adapter = self._file_adapter_factory(client)
            file_record = adapter.get_file_record(session.file_id)
            prepared = prepare_media_evidence(
                byte_stream=adapter.iter_download_bytes(file_record),
                request_id=f"{context.team_id}-{context.channel_id}-{context.thread_ts}",
                untrusted_filename=file_record.name,
                temp_root=self._temp_root,
                max_bytes=self._max_video_bytes,
                max_duration_seconds=self._max_video_duration_seconds,
                transcriber=self._transcriber,
            )
            workspace = prepared.workspace

            if prepared.audio_evidence.transcription_failed:
                raise TranscriptionFailureError(prepared.audio_evidence.detail)

            analyzer = self._analyzer_factory()
            result = analyzer.analyze(build_analysis_request(prepared))
            self._post_message(
                client,
                channel=context.channel_id,
                thread_ts=context.thread_ts,
                text=render_explanation_reply(result=result, audio_evidence=prepared.audio_evidence),
            )
            terminal_state = "success"
        except Exception as exc:
            self._post_message(
                client,
                channel=context.channel_id,
                thread_ts=context.thread_ts,
                text=failure_message_for_exception(exc),
            )
        finally:
            if workspace is not None:
                workspace.cleanup(state=terminal_state, logger=self._logger)

    def _post_message(self, client: Any, *, channel: str, thread_ts: str, text: str) -> None:
        try:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
        except Exception as exc:
            self._logger.error("Slack message publish failed during explanation: %s", redact_sensitive(exc))


def build_analysis_request(prepared: PreparedMediaEvidence) -> AnalysisRequest:
    frames = tuple(
        _frame_evidence(frame.path, frame.label, frame.timestamp_seconds)
        for frame in prepared.frames
        if frame.path.exists()
    )
    if not frames:
        raise MediaExtractionError("FFmpeg could not extract a representative frame.")

    return AnalysisRequest(
        user_request=(
            "Explain this video in English with a short summary, key points, and timestamps only when the evidence supports them."
        ),
        frames=frames,
        transcript=(
            TranscriptEvidence(text=prepared.audio_evidence.transcript_text)
            if prepared.audio_evidence.transcript_text
            else None
        ),
    )


def _frame_evidence(path: Path, label: str, timestamp_seconds: float | None) -> FrameEvidence:
    return FrameEvidence(
        label=label,
        observation="Representative frame captured from the uploaded video.",
        timestamp_seconds=timestamp_seconds,
        image_media_type="image/png",
        image_base64=base64.b64encode(path.read_bytes()).decode("ascii"),
    )


def render_explanation_reply(*, result: AnalysisResult, audio_evidence: AudioEvidence) -> str:
    lines = [
        "Summary:",
        result.summary,
        "",
        "Key points:",
        *[f"- {item}" for item in result.key_points],
    ]

    if result.timestamps_available and result.timestamps:
        lines.extend(["", "Timestamps:"])
        for item in result.timestamps:
            if item.end_seconds is None:
                lines.append(f"- {_format_seconds(item.start_seconds)} — {item.label}")
            else:
                lines.append(
                    f"- {_format_seconds(item.start_seconds)} to {_format_seconds(item.end_seconds)} — {item.label}"
                )
    else:
        lines.extend(["", "Timestamps were unavailable from the available evidence."])

    if audio_evidence.detail:
        lines.extend(["", f"Evidence note: {audio_evidence.detail}"])

    return "\n".join(lines)


def _format_seconds(value: float) -> str:
    total_seconds = max(int(value), 0)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def failure_message_for_exception(exc: Exception) -> str:
    if isinstance(exc, AnalysisConfigurationError):
        return "I can't analyze this video yet because the Claude configuration is missing. Please add ANTHROPIC_API_KEY and try again."
    if isinstance(exc, SlackAdapterError):
        return "I couldn't download this Slack upload safely. Please try again from this thread."
    if isinstance(exc, MediaValidationError):
        return str(exc)
    if isinstance(exc, MediaProbeError):
        return "I couldn't inspect this MP4 safely with FFprobe, so the explanation could not continue."
    if isinstance(exc, TranscriptionFailureError):
        return "I couldn't prepare transcript evidence safely, so the explanation could not continue."
    if isinstance(exc, MediaExtractionError):
        return "I couldn't prepare media evidence safely with FFmpeg, so the explanation could not continue."
    if isinstance(exc, AnalysisTimeoutError):
        return "Claude took too long to analyze this video, so no explanation was posted. Please try again."
    if isinstance(exc, AnalysisProviderError):
        return "Claude couldn't analyze this video successfully, so no explanation was posted. Please try again."
    if isinstance(exc, AnalysisInvalidResponseError):
        return "Claude returned an invalid explanation format, so no explanation was posted. Please try again."
    if isinstance(exc, MediaPipelineError):
        return "I couldn't prepare the video evidence safely, so the explanation could not continue."
    return "I couldn't explain this video safely. Please try again in this thread."
