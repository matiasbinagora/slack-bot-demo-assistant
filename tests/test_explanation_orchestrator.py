from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from slack_video_assistant.claude_analysis import (
    AnalysisBudgetError,
    AnalysisConfigurationError,
    AnalysisInvalidResponseError,
    AnalysisProviderError,
    AnalysisResult,
    AnalysisTimeoutError,
    AnalysisTimestamp,
    build_prompt_envelope,
)
from slack_video_assistant.explanation_orchestrator import (
    ExplanationOrchestrator,
    SegmentAnalysisSuccess,
    SegmentAnalysisUnavailable,
    analyze_video_segments,
    build_analysis_request,
    failure_message_for_exception,
    render_explanation_replies,
)
from slack_video_assistant.media_pipeline import (
    AudioEvidence,
    EvidenceStatus,
    ExtractedFrame,
    MediaExtractionError,
    MediaWorkspace,
    PreparedMediaEvidence,
    PreparedSegmentEvidence,
    SegmentInterval,
    VideoMetadata,
)
from slack_video_assistant.session_store import SessionKey, SessionStatus, ThreadSession
from slack_video_assistant.slack_file_adapter import SlackAdapterError, SlackFileRecord


class FakeSlackClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat_postMessage(self, **payload: Any) -> None:
        self.calls.append(payload)


class ExplodingSlackClient(FakeSlackClient):
    def chat_postMessage(self, **payload: Any) -> None:
        raise RuntimeError("token=xoxb-secret-token url=https://files.slack.com/private path=/tmp/private/video.mp4")


class FakeDownloadResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.stream_calls = 0

    def iter_bytes(self, chunk_size: int = 65536):
        del chunk_size
        self.stream_calls += 1
        yield self.payload


class FakeAdapter:
    def __init__(self, payload: bytes, *, file_id: str = "F1", name: str = "clip.mp4") -> None:
        self.record = SlackFileRecord(
            file_id=file_id,
            name=name,
            mimetype="video/mp4",
            filetype="mp4",
            url_private_download="https://files.slack.com/files-pri/T1-F1/download",
            raw={"id": file_id},
        )
        self.response = FakeDownloadResponse(payload)
        self.get_calls = 0

    def get_file_record(self, file_id: str) -> SlackFileRecord:
        self.get_calls += 1
        return self.record

    def iter_download_bytes(self, file_record: SlackFileRecord):
        del file_record
        return self.response.iter_bytes()


class DeferredExecutor:
    def __init__(self) -> None:
        self.jobs: list[Any] = []

    def submit(self, job) -> None:
        self.jobs.append(job)


class ImmediateExecutor:
    def submit(self, job) -> None:
        job()


@dataclass
class SequenceAnalyzer:
    outcomes: list[AnalysisResult | Exception]
    calls: list[Any]

    def analyze(self, request):
        self.calls.append(request)
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class BudgetInspectingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.envelopes: list[Any] = []

    def analyze(self, request):
        self.calls.append(request)
        envelope = build_prompt_envelope(request)
        self.envelopes.append(envelope)
        return AnalysisResult(
            summary=f"Summary for call {len(self.calls)}.",
            key_points=(f"Point {len(self.calls)}.",),
            timestamps_available=True,
            timestamps=(AnalysisTimestamp(label="Moment", start_seconds=0.0, end_seconds=1.0),),
        )


def make_session() -> ThreadSession:
    return ThreadSession(
        key=SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001"),
        file_id="F1",
        status=SessionStatus.EXPLANATION_REQUESTED,
    )


def make_prepared_media(tmp_path: Path, *, duration_seconds: float = 25.0, transcript_text: str | None = None) -> PreparedMediaEvidence:
    workspace = MediaWorkspace.create(temp_root=tmp_path / "workspaces", request_id="explain")
    source_path = workspace.source_path
    source_path.write_bytes(b"fake-mp4")
    return PreparedMediaEvidence(
        workspace=workspace,
        source_path=source_path,
        metadata=VideoMetadata(
            duration_seconds=duration_seconds,
            width=32,
            height=32,
            container_names=("mp4",),
            video_codec="h264",
            audio_codec="aac",
            has_audio=True,
        ),
        frames=(),
        audio_evidence=AudioEvidence(
            status=EvidenceStatus.DEGRADED,
            detail="Audio transcript is available, but reliable timestamps are unavailable.",
            transcript_text=transcript_text,
            timestamps_available=False,
        ),
    )


def make_segment(interval: SegmentInterval, workspace: MediaWorkspace, *, timestamp_seconds: float | None = None) -> PreparedSegmentEvidence:
    frame_path = workspace.controlled_path(f"segments/segment-{interval.index:02d}/frames/frame-01.jpg")
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_bytes(b"jpeg-bytes")
    return PreparedSegmentEvidence(
        interval=interval,
        frames=(
            ExtractedFrame(
                path=frame_path,
                label=f"segment-{interval.index:02d}-frame-01",
                timestamp_seconds=interval.start_seconds if timestamp_seconds is None else timestamp_seconds,
            ),
        ),
    )


def test_explanation_post_message_logs_redacted_exception(caplog) -> None:
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: None,
        executor=ImmediateExecutor(),
        logger=logging.getLogger("tests.explanation.logging"),
    )

    with caplog.at_level(logging.ERROR, logger="tests.explanation.logging"):
        succeeded = orchestrator._post_message(
            ExplodingSlackClient(),
            channel="C1",
            thread_ts="170.0001",
            text="hello",
        )

    assert succeeded is False
    assert "xoxb-secret-token" not in caplog.text
    assert "https://files.slack.com/private" not in caplog.text
    assert "/tmp/private/video.mp4" not in caplog.text
    assert "[REDACTED_TOKEN]" in caplog.text
    assert "[REDACTED_URL]" in caplog.text
    assert "[REDACTED_PATH]" in caplog.text


def test_explain_acknowledges_and_schedules_background_job_without_running_inline(tmp_path: Path, monkeypatch) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=25.0)
    adapter = FakeAdapter(b"fake-mp4")
    client = FakeSlackClient()
    executor = DeferredExecutor()
    analyzer_calls: list[Any] = []
    analyzer = SequenceAnalyzer(
        outcomes=[
            AnalysisResult(summary="One.", key_points=("P1",), timestamps_available=False, timestamps=()),
            AnalysisResult(summary="Two.", key_points=("P2",), timestamps_available=False, timestamps=()),
            AnalysisResult(summary="Three.", key_points=("P3",), timestamps_available=False, timestamps=()),
        ],
        calls=analyzer_calls,
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.prepare_media_evidence",
        lambda **kwargs: prepared,
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        lambda source_path, workspace, interval: make_segment(interval, workspace),
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=executor,
        logger=logging.getLogger("tests.explanation.queue"),
        temp_root=tmp_path / "work",
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert len(executor.jobs) == 1
    assert adapter.get_calls == 0
    assert adapter.response.stream_calls == 0
    assert analyzer_calls == []
    assert client.calls == []

    executor.jobs[0]()

    assert adapter.get_calls == 1
    assert adapter.response.stream_calls == 0
    assert len(analyzer_calls) == 3
    assert client.calls[-1]["channel"] == "C1"
    assert client.calls[-1]["thread_ts"] == "170.0001"
    assert "Interval 00:20 to 00:25" in client.calls[-1]["text"]

    prepared.workspace.cleanup(state="success")


def test_build_analysis_request_uses_segment_local_controlled_frame_evidence(tmp_path: Path) -> None:
    workspace = MediaWorkspace.create(temp_root=tmp_path / "workspaces", request_id="request-test")
    interval = SegmentInterval(index=1, start_seconds=10.0, end_seconds=20.0)
    segment = make_segment(interval, workspace, timestamp_seconds=12.5)

    request = build_analysis_request(segment)

    assert request.user_request.startswith("Explain this video interval in English")
    assert "00:10 to 00:20" in request.user_request
    assert request.transcript is None
    assert request.frames[0].image_base64 is not None
    assert request.frames[0].image_media_type == "image/jpeg"
    assert request.frames[0].timestamp_seconds == 12.5
    workspace.cleanup(state="success")


def test_segment_analysis_uses_independent_local_requests_and_budget_guards(tmp_path: Path, monkeypatch) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=25.0, transcript_text="Global transcript.")
    analyzer = BudgetInspectingAnalyzer()

    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        lambda source_path, workspace, interval: make_segment(interval, workspace),
    )

    outcomes = analyze_video_segments(prepared=prepared, analyzer=analyzer)

    assert len(outcomes) == 3
    assert len(analyzer.calls) == 3
    assert all(request.transcript is None for request in analyzer.calls)
    assert all(len(request.frames) <= 3 for request in analyzer.calls)
    assert all("image_base64" not in envelope.user_prompt for envelope in analyzer.envelopes)
    assert analyzer.calls[0].user_request != analyzer.calls[1].user_request
    assert "00:00 to 00:10" in analyzer.calls[0].user_request
    assert "00:10 to 00:20" in analyzer.calls[1].user_request
    assert isinstance(outcomes[0], SegmentAnalysisSuccess)

    prepared.workspace.cleanup(state="success")


def test_render_explanation_replies_formats_chronological_sections_and_supported_timestamps() -> None:
    interval_results = (
        SegmentAnalysisSuccess(
            interval=SegmentInterval(index=1, start_seconds=0.0, end_seconds=10.0),
            result=AnalysisResult(
                summary="A dashboard appears.",
                key_points=("The dashboard loads.",),
                timestamps_available=True,
                timestamps=(AnalysisTimestamp(label="Dashboard loads", start_seconds=1.0, end_seconds=2.0),),
            ),
        ),
        SegmentAnalysisSuccess(
            interval=SegmentInterval(index=2, start_seconds=10.0, end_seconds=20.0),
            result=AnalysisResult(
                summary="A chart is highlighted.",
                key_points=("The presenter points at a chart.",),
                timestamps_available=False,
                timestamps=(),
            ),
        ),
    )

    messages = render_explanation_replies(
        interval_results=interval_results,
        audio_evidence=AudioEvidence(
            status=EvidenceStatus.DEGRADED,
            detail="Audio transcript is available, but reliable timestamps are unavailable.",
            transcript_text="Global transcript.",
        ),
    )

    assert len(messages) == 1
    reply = messages[0]
    assert "Interval 00:00 to 00:10" in reply
    assert "Interval 00:10 to 00:20" in reply
    assert "Summary: A dashboard appears." in reply
    assert "Supported timestamps:" in reply
    assert "- 00:01 to 00:02 — Dashboard loads" in reply
    assert "Supported timestamps were unavailable for this interval." in reply
    assert "Transcript evidence was not reused across segments." in reply


def test_partial_failures_render_unavailable_intervals_while_later_segments_continue(tmp_path: Path, monkeypatch) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=65.0)
    adapter = FakeAdapter(b"fake-mp4")
    client = FakeSlackClient()
    analyzer = SequenceAnalyzer(
        outcomes=[
            AnalysisResult(summary="Opening.", key_points=("Start",), timestamps_available=False, timestamps=()),
            AnalysisTimeoutError("timeout"),
            AnalysisResult(summary="Closing.", key_points=("End",), timestamps_available=False, timestamps=()),
        ],
        calls=[],
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.prepare_media_evidence",
        lambda **kwargs: prepared,
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        lambda source_path, workspace, interval: make_segment(interval, workspace),
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger("tests.explanation.partial"),
        temp_root=tmp_path / "work",
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert len(analyzer.calls) == 3
    assert len(client.calls) == 1
    reply = client.calls[0]["text"]
    assert "Interval 00:00 to 00:30" in reply
    assert "Interval 00:30 to 01:00\nUnavailable: Analysis was unavailable for this interval." in reply
    assert "Interval 01:00 to 01:05" in reply
    prepared.workspace.cleanup(state="success")


def test_all_segment_failures_post_safe_failure_without_fabricated_partial_output(tmp_path: Path, monkeypatch) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=25.0)
    adapter = FakeAdapter(b"fake-mp4")
    client = FakeSlackClient()
    analyzer = SequenceAnalyzer(
        outcomes=[AnalysisTimeoutError("timeout")] * 3,
        calls=[],
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.prepare_media_evidence",
        lambda **kwargs: prepared,
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        lambda source_path, workspace, interval: make_segment(interval, workspace),
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger("tests.explanation.all_fail"),
        temp_root=tmp_path / "work",
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert len(client.calls) == 1
    assert client.calls[0]["text"] == "Claude couldn't analyze this video successfully, so no explanation was posted. Please try again."
    prepared.workspace.cleanup(state="success")


def test_frame_extraction_failure_marks_only_that_interval_unavailable(tmp_path: Path, monkeypatch) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=25.0)
    analyzer = SequenceAnalyzer(
        outcomes=[
            AnalysisResult(summary="One.", key_points=("P1",), timestamps_available=False, timestamps=()),
            AnalysisResult(summary="Three.", key_points=("P3",), timestamps_available=False, timestamps=()),
        ],
        calls=[],
    )

    def fake_extract_segment_frames(source_path, workspace, interval):
        del source_path
        if interval.index == 2:
            raise MediaExtractionError("ffmpeg")
        return make_segment(interval, workspace)

    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        fake_extract_segment_frames,
    )

    outcomes = analyze_video_segments(prepared=prepared, analyzer=analyzer)

    assert isinstance(outcomes[1], SegmentAnalysisUnavailable)
    assert outcomes[1].detail == "Frames were unavailable for this interval."
    assert len(analyzer.calls) == 2
    prepared.workspace.cleanup(state="success")


def test_first_segment_frame_extraction_failure_is_fatal(tmp_path: Path, monkeypatch) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=25.0)
    analyzer = SequenceAnalyzer(
        outcomes=[
            AnalysisResult(summary="unused", key_points=("unused",), timestamps_available=False, timestamps=()),
        ],
        calls=[],
    )

    def fake_extract_segment_frames(source_path, workspace, interval):
        del source_path, workspace, interval
        raise MediaExtractionError("ffmpeg unavailable")

    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        fake_extract_segment_frames,
    )

    with pytest.raises(MediaExtractionError, match="ffmpeg unavailable"):
        analyze_video_segments(prepared=prepared, analyzer=analyzer)

    assert analyzer.calls == []
    prepared.workspace.cleanup(state="success")


@pytest.mark.parametrize(
    "error",
    [
        AnalysisTimeoutError("timeout"),
        AnalysisBudgetError("budget"),
        AnalysisProviderError("provider"),
        AnalysisInvalidResponseError("invalid"),
    ],
)
def test_segment_local_analyzer_failures_continue_with_later_intervals(tmp_path: Path, monkeypatch, error: Exception) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=25.0)
    analyzer = SequenceAnalyzer(
        outcomes=[
            AnalysisResult(summary="One.", key_points=("P1",), timestamps_available=False, timestamps=()),
            error,
            AnalysisResult(summary="Three.", key_points=("P3",), timestamps_available=False, timestamps=()),
        ],
        calls=[],
    )

    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        lambda source_path, workspace, interval: make_segment(interval, workspace),
    )

    outcomes = analyze_video_segments(prepared=prepared, analyzer=analyzer)

    assert len(outcomes) == 3
    assert isinstance(outcomes[1], SegmentAnalysisUnavailable)
    assert outcomes[1].detail == "Analysis was unavailable for this interval."
    assert isinstance(outcomes[2], SegmentAnalysisSuccess)
    prepared.workspace.cleanup(state="success")


def test_failure_message_mapping_covers_safe_error_paths() -> None:
    cases = [
        (AnalysisConfigurationError("missing"), "I can't analyze this video yet because the Claude configuration is missing. Please add ANTHROPIC_API_KEY and try again."),
        (SlackAdapterError("download"), "I couldn't download this Slack upload safely. Please try again from this thread."),
        (MediaExtractionError("ffmpeg"), "I couldn't prepare media evidence safely with FFmpeg, so the explanation could not continue."),
        (AnalysisTimeoutError("timeout"), "Claude took too long to analyze this video, so no explanation was posted. Please try again."),
        (AnalysisBudgetError("budget"), "I couldn't fit this video evidence within the safe Claude request budget, so no explanation was posted. Please try a shorter or simpler clip in this thread."),
        (AnalysisProviderError("provider"), "Claude couldn't analyze this video successfully, so no explanation was posted. Please try again."),
        (AnalysisInvalidResponseError("invalid"), "Claude returned an invalid explanation format, so no explanation was posted. Please try again."),
    ]

    for exc, expected in cases:
        assert failure_message_for_exception(exc) == expected


def test_publish_failure_is_logged_and_cleanup_still_runs(tmp_path: Path, monkeypatch, caplog) -> None:
    prepared = make_prepared_media(tmp_path, duration_seconds=25.0)
    adapter = FakeAdapter(b"fake-mp4")
    analyzer = SequenceAnalyzer(
        outcomes=[
            AnalysisResult(summary="One.", key_points=("P1",), timestamps_available=False, timestamps=()),
            AnalysisResult(summary="Two.", key_points=("P2",), timestamps_available=False, timestamps=()),
            AnalysisResult(summary="Three.", key_points=("P3",), timestamps_available=False, timestamps=()),
        ],
        calls=[],
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.prepare_media_evidence",
        lambda **kwargs: prepared,
    )
    monkeypatch.setattr(
        "slack_video_assistant.explanation_orchestrator.extract_segment_frames",
        lambda source_path, workspace, interval: make_segment(interval, workspace),
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger("tests.explanation.publish_failure"),
        temp_root=tmp_path / "work",
    )

    with caplog.at_level(logging.ERROR, logger="tests.explanation.publish_failure"):
        orchestrator.enqueue(client=ExplodingSlackClient(), session=make_session())

    assert "Slack message publish failed during explanation" in caplog.text
    assert "[REDACTED_TOKEN]" in caplog.text
    assert not prepared.workspace.root.exists()
