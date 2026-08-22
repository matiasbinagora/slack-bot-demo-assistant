from __future__ import annotations

import base64
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from slack_video_assistant.claude_analysis import (
    AnalysisBudgetError,
    AnalysisConfigurationError,
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    AnalysisRequest,
    AnalysisResult,
    AnalysisTimestamp,
    AnalysisTimeoutError,
    ClaudeAnalyzer,
    FrameEvidence,
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
    PreparedSegmentEvidence,
    SegmentInterval,
    extract_segment_frames,
    plan_segment_intervals,
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
                extract_representative_frames=False,
                transcriber=self._transcriber,
            )
            workspace = prepared.workspace
            analyzer = self._analyzer_factory()
            interval_results = analyze_video_segments(
                prepared=prepared,
                analyzer=analyzer,
            )
            publish_succeeded = True
            for message in render_explanation_replies(
                interval_results=interval_results,
                audio_evidence=prepared.audio_evidence,
            ):
                publish_succeeded = (
                    self._post_message(
                        client,
                        channel=context.channel_id,
                        thread_ts=context.thread_ts,
                        text=message,
                    )
                    and publish_succeeded
                )
            terminal_state = "success" if publish_succeeded else "publish_failure"
        except Exception as exc:
            publish_succeeded = self._post_message(
                client,
                channel=context.channel_id,
                thread_ts=context.thread_ts,
                text=failure_message_for_exception(exc),
            )
            terminal_state = "failure" if publish_succeeded else "publish_failure"
        finally:
            if workspace is not None:
                workspace.cleanup(state=terminal_state, logger=self._logger)

    def _post_message(self, client: Any, *, channel: str, thread_ts: str, text: str) -> bool:
        try:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
            return True
        except Exception as exc:
            self._logger.error("Slack message publish failed during explanation: %s", redact_sensitive(exc))
            return False


@dataclass(frozen=True)
class SegmentAnalysisSuccess:
    interval: SegmentInterval
    result: AnalysisResult


@dataclass(frozen=True)
class SegmentAnalysisUnavailable:
    interval: SegmentInterval
    detail: str


SegmentAnalysisOutcome = SegmentAnalysisSuccess | SegmentAnalysisUnavailable


def analyze_video_segments(
    *,
    prepared: PreparedMediaEvidence,
    analyzer: ClaudeAnalyzer,
) -> tuple[SegmentAnalysisOutcome, ...]:
    intervals = plan_segment_intervals(prepared.metadata.duration_seconds)
    outcomes: list[SegmentAnalysisOutcome] = []

    for interval in intervals:
        try:
            segment = extract_segment_frames(
                prepared.source_path,
                workspace=prepared.workspace,
                interval=interval,
            )
            request = build_analysis_request(segment)
            result = analyzer.analyze(request)
        except (AnalysisTimeoutError, AnalysisBudgetError, AnalysisProviderError, AnalysisInvalidResponseError):
            outcomes.append(
                SegmentAnalysisUnavailable(
                    interval=interval,
                    detail="Analysis was unavailable for this interval.",
                )
            )
            continue
        except MediaExtractionError:
            if not outcomes:
                raise
            outcomes.append(
                SegmentAnalysisUnavailable(
                    interval=interval,
                    detail="Frames were unavailable for this interval.",
                )
            )
            continue
        outcomes.append(SegmentAnalysisSuccess(interval=interval, result=result))

    if not any(isinstance(outcome, SegmentAnalysisSuccess) for outcome in outcomes):
        raise AnalysisProviderError("No interval produced a valid analysis result.")
    return tuple(outcomes)


def build_analysis_request(prepared: PreparedSegmentEvidence) -> AnalysisRequest:
    frames = tuple(
        _frame_evidence(frame.path, frame.label, frame.timestamp_seconds)
        for frame in prepared.frames
        if frame.path.exists()
    )
    if not frames:
        raise MediaExtractionError("FFmpeg could not extract a representative frame.")

    return AnalysisRequest(
        user_request=(
            "Explain this video interval in English with a short summary, key points, and timestamps only when the evidence supports them. "
            f"This interval covers {_format_seconds(prepared.interval.start_seconds)} to {_format_seconds(prepared.interval.end_seconds)}."
        ),
        frames=frames,
        transcript=None,
    )


def _frame_evidence(path: Path, label: str, timestamp_seconds: float | None) -> FrameEvidence:
    return FrameEvidence(
        label=label,
        observation="Representative frame captured from the uploaded video.",
        timestamp_seconds=timestamp_seconds,
        image_media_type="image/jpeg",
        image_base64=base64.b64encode(path.read_bytes()).decode("ascii"),
    )


def render_explanation_replies(
    *, interval_results: tuple[SegmentAnalysisOutcome, ...], audio_evidence: AudioEvidence
) -> tuple[str, ...]:
    section_texts = [render_interval_section(outcome) for outcome in interval_results]
    if audio_evidence.detail:
        section_texts.append(f"Evidence note: {_render_audio_evidence_note(audio_evidence)}")

    messages: list[str] = []
    current_sections: list[str] = []
    max_message_chars = 3500
    for section in section_texts:
        candidate = "\n\n".join([*current_sections, section])
        if current_sections and len(candidate) > max_message_chars:
            messages.append("\n\n".join(current_sections))
            current_sections = [section]
        else:
            current_sections.append(section)

    if current_sections:
        messages.append("\n\n".join(current_sections))
    return tuple(messages)


def render_interval_section(outcome: SegmentAnalysisOutcome) -> str:
    header = (
        f"Interval {_format_seconds(outcome.interval.start_seconds)} to "
        f"{_format_seconds(outcome.interval.end_seconds)}"
    )
    if isinstance(outcome, SegmentAnalysisUnavailable):
        return f"{header}\nUnavailable: {outcome.detail}"

    result = outcome.result
    lines = [
        header,
        f"Summary: {result.summary}",
        "Key points:",
        *[f"- {item}" for item in result.key_points],
    ]
    if result.timestamps_available and result.timestamps:
        lines.append("Supported timestamps:")
        for item in result.timestamps:
            lines.append(f"- {_format_timestamp(item)} — {item.label}")
    else:
        lines.append("Supported timestamps were unavailable for this interval.")
    return "\n".join(lines)


def _render_audio_evidence_note(audio_evidence: AudioEvidence) -> str:
    if audio_evidence.transcript_text:
        return "This explanation used sampled video frames for each interval. Transcript evidence was not reused across segments."
    return audio_evidence.detail


def _format_timestamp(item: AnalysisTimestamp) -> str:
    if item.end_seconds is None:
        return _format_seconds(item.start_seconds)
    return f"{_format_seconds(item.start_seconds)} to {_format_seconds(item.end_seconds)}"


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
    if isinstance(exc, MediaExtractionError):
        return "I couldn't prepare media evidence safely with FFmpeg, so the explanation could not continue."
    if isinstance(exc, AnalysisTimeoutError):
        return "Claude took too long to analyze this video, so no explanation was posted. Please try again."
    if isinstance(exc, AnalysisBudgetError):
        return "I couldn't fit this video evidence within the safe Claude request budget, so no explanation was posted. Please try a shorter or simpler clip in this thread."
    if isinstance(exc, AnalysisProviderError):
        return "Claude couldn't analyze this video successfully, so no explanation was posted. Please try again."
    if isinstance(exc, AnalysisInvalidResponseError):
        return "Claude returned an invalid explanation format, so no explanation was posted. Please try again."
    if isinstance(exc, MediaPipelineError):
        return "I couldn't prepare the video evidence safely, so the explanation could not continue."
    return "I couldn't explain this video safely. Please try again in this thread."
