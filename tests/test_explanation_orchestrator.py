from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slack_video_assistant.claude_analysis import (
    MAX_TOTAL_IMAGE_BASE64_CHARS,
    MAX_USER_PROMPT_CHARS,
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
    build_analysis_request,
    failure_message_for_exception,
)
from slack_video_assistant.media_pipeline import (
    AudioEvidence,
    EvidenceStatus,
    MediaExtractionError,
    MediaProbeError,
    MediaValidationError,
    PreparedMediaEvidence,
    TranscriptionResult,
    prepare_media_evidence,
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
        self.stream_calls += 1
        yield self.payload


class FakeAdapter:
    def __init__(self, payload: bytes, *, file_id: str = 'F1', name: str = 'clip.mp4') -> None:
        self.record = SlackFileRecord(
            file_id=file_id,
            name=name,
            mimetype='video/mp4',
            filetype='mp4',
            url_private_download='https://files.slack.com/files-pri/T1-F1/download',
            raw={'id': file_id},
        )
        self.response = FakeDownloadResponse(payload)
        self.get_calls = 0

    def get_file_record(self, file_id: str) -> SlackFileRecord:
        self.get_calls += 1
        return self.record

    def iter_download_bytes(self, file_record: SlackFileRecord):
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
class CapturingAnalyzer:
    result: AnalysisResult
    calls: list[Any]

    def analyze(self, request):
        self.calls.append(request)
        return self.result


class BudgetCheckingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def analyze(self, request):
        self.calls.append(request)
        build_prompt_envelope(request)
        raise AssertionError("budget checker should fail before provider execution")


class FakeTranscriber:
    def __init__(self, *, text: str = 'Detected narration.', timestamps_available: bool = True) -> None:
        self.text = text
        self.timestamps_available = timestamps_available

    def transcribe(self, *, audio_path: Path) -> TranscriptionResult:
        return TranscriptionResult(self.text, self.timestamps_available)


class ExplodingTranscriber:
    def transcribe(self, *, audio_path: Path) -> TranscriptionResult:
        raise RuntimeError('boom')


class ProviderRejectingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def analyze(self, request):
        self.calls.append(request)
        raise AnalysisProviderError('provider rejected request')


def make_session() -> ThreadSession:
    return ThreadSession(
        key=SessionKey(team_id='T1', channel_id='C1', thread_ts='170.0001'),
        file_id='F1',
        status=SessionStatus.EXPLANATION_REQUESTED,
    )


def build_mp4_fixture(
    directory: Path,
    *,
    name: str,
    with_audio: bool,
    duration_seconds: int,
    size: str = '32x32',
    fps: int = 5,
) -> Path:
    output_path = directory / f'{name}.mp4'
    command = [
        'ffmpeg',
        '-loglevel',
        'error',
        '-y',
        '-f',
        'lavfi',
        '-i',
        f'testsrc=size={size}:rate={fps}:duration={duration_seconds}',
    ]
    if with_audio:
        command.extend(['-f', 'lavfi', '-i', f'sine=frequency=880:duration={duration_seconds}'])
    command.extend(['-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '35'])
    if with_audio:
        command.extend(['-c:a', 'aac', '-shortest'])
    command.append(str(output_path))
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output_path




def test_explanation_post_message_logs_redacted_exception(caplog) -> None:
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: None,
        executor=ImmediateExecutor(),
        logger=logging.getLogger('tests.explanation.logging'),
    )

    with caplog.at_level(logging.ERROR, logger='tests.explanation.logging'):
        orchestrator._post_message(
            ExplodingSlackClient(),
            channel='C1',
            thread_ts='170.0001',
            text='hello',
        )

    assert 'xoxb-secret-token' not in caplog.text
    assert 'https://files.slack.com/private' not in caplog.text
    assert '/tmp/private/video.mp4' not in caplog.text
    assert '[REDACTED_TOKEN]' in caplog.text
    assert '[REDACTED_URL]' in caplog.text
    assert '[REDACTED_PATH]' in caplog.text


def test_explain_acknowledges_and_schedules_background_job_without_running_inline(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='queued', with_audio=True, duration_seconds=1)
    adapter = FakeAdapter(fixture.read_bytes())
    client = FakeSlackClient()
    executor = DeferredExecutor()
    analyzer_calls: list[Any] = []
    analyzer = CapturingAnalyzer(
        result=AnalysisResult(
            summary='A presenter opens a dashboard.',
            key_points=('The dashboard appears.',),
            timestamps_available=True,
            timestamps=(AnalysisTimestamp(label='Dashboard opens', start_seconds=0.0),),
        ),
        calls=analyzer_calls,
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=executor,
        logger=logging.getLogger('tests.explanation.queue'),
        temp_root=tmp_path / 'work',
        transcriber=FakeTranscriber(),
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert len(executor.jobs) == 1
    assert adapter.get_calls == 0
    assert adapter.response.stream_calls == 0
    assert analyzer_calls == []
    assert client.calls == []

    executor.jobs[0]()

    assert adapter.get_calls == 1
    assert adapter.response.stream_calls == 1
    assert len(analyzer_calls) == 1
    assert client.calls[-1]['channel'] == 'C1'
    assert client.calls[-1]['thread_ts'] == '170.0001'
    assert 'Summary:' in client.calls[-1]['text']




def test_explanation_creates_missing_configured_temp_root_and_posts_success(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='missing-root', with_audio=True, duration_seconds=1)
    temp_root = tmp_path / 'missing' / 'nested-work'
    adapter = FakeAdapter(fixture.read_bytes())
    client = FakeSlackClient()
    analyzer = CapturingAnalyzer(
        result=AnalysisResult(
            summary='A presenter opens a dashboard.',
            key_points=('The dashboard appears.',),
            timestamps_available=False,
            timestamps=(),
        ),
        calls=[],
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger('tests.explanation.temp_root'),
        temp_root=temp_root,
        transcriber=FakeTranscriber(timestamps_available=False),
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert temp_root.exists() is True
    assert client.calls[0]['thread_ts'] == '170.0001'
    assert 'Summary:' in client.calls[0]['text']


def test_explanation_success_posts_summary_key_points_and_timestamps_with_controlled_evidence(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='success', with_audio=True, duration_seconds=2)
    adapter = FakeAdapter(fixture.read_bytes())
    client = FakeSlackClient()
    analyzer_calls: list[Any] = []
    analyzer = CapturingAnalyzer(
        result=AnalysisResult(
            summary='The speaker introduces a dashboard.',
            key_points=('A dashboard opens.', 'Charts are highlighted.'),
            timestamps_available=True,
            timestamps=(AnalysisTimestamp(label='Dashboard opens', start_seconds=1.0, end_seconds=2.0),),
        ),
        calls=analyzer_calls,
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger('tests.explanation.success'),
        temp_root=tmp_path / 'work',
        transcriber=FakeTranscriber(text='Detected narration.', timestamps_available=True),
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert len(client.calls) == 1
    reply = client.calls[0]['text']
    assert 'Summary:' in reply
    assert 'Key points:' in reply
    assert 'Timestamps:' in reply
    assert '01:00' not in reply
    assert '00:01 to 00:02 — Dashboard opens' in reply
    assert 'Evidence note: Audio transcript and timestamps are available.' in reply
    request = analyzer_calls[0]
    assert request.transcript is not None
    assert request.frames[0].image_base64 is not None
    assert request.frames[0].image_media_type == 'image/jpeg'
    assert not hasattr(request.frames[0], 'path')


def test_explanation_success_without_timestamps_reports_unavailable_status(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='degraded', with_audio=True, duration_seconds=1)
    adapter = FakeAdapter(fixture.read_bytes())
    client = FakeSlackClient()
    analyzer = CapturingAnalyzer(
        result=AnalysisResult(
            summary='The clip shows a quick app walkthrough.',
            key_points=('The app opens.',),
            timestamps_available=False,
            timestamps=(),
        ),
        calls=[],
    )
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger('tests.explanation.degraded'),
        temp_root=tmp_path / 'work',
        transcriber=FakeTranscriber(timestamps_available=False),
    )

    orchestrator.enqueue(client=client, session=make_session())

    reply = client.calls[0]['text']
    assert 'Timestamps:' not in reply
    assert 'Timestamps were unavailable from the available evidence.' in reply
    assert 'Evidence note: Audio transcript is available, but reliable timestamps are unavailable.' in reply


def test_explanation_transcription_failure_posts_safe_thread_error(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='transcription-failure', with_audio=True, duration_seconds=1)
    adapter = FakeAdapter(fixture.read_bytes())
    client = FakeSlackClient()
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: CapturingAnalyzer(
            result=AnalysisResult(summary='unused', key_points=('unused',), timestamps_available=False, timestamps=()),
            calls=[],
        ),
        executor=ImmediateExecutor(),
        logger=logging.getLogger('tests.explanation.transcription'),
        temp_root=tmp_path / 'work',
        transcriber=ExplodingTranscriber(),
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert client.calls[0]["text"] == "I couldn't prepare transcript evidence safely, so the explanation could not continue."


def test_build_analysis_request_uses_controlled_frame_and_transcript_evidence(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='request', with_audio=True, duration_seconds=1)
    temp_root = tmp_path / 'workspaces'
    prepared = prepare_media_evidence(
        byte_stream=[fixture.read_bytes()],
        request_id='request-test',
        untrusted_filename='clip.mp4',
        temp_root=temp_root,
        transcriber=FakeTranscriber(text='Narration.', timestamps_available=True),
    )

    assert temp_root.exists() is True

    request = build_analysis_request(prepared)

    assert request.user_request.startswith('Explain this video in English')
    assert request.transcript is not None
    assert request.transcript.text == 'Narration.'
    assert request.frames[0].image_base64 is not None
    assert request.frames[0].image_media_type == 'image/jpeg'
    prepared.workspace.cleanup(state='success')


def test_failure_message_mapping_covers_safe_error_paths() -> None:
    cases = [
        (AnalysisConfigurationError('missing'), "I can't analyze this video yet because the Claude configuration is missing. Please add ANTHROPIC_API_KEY and try again."),
        (SlackAdapterError('download'), "I couldn't download this Slack upload safely. Please try again from this thread."),
        (MediaValidationError('bad mp4'), 'bad mp4'),
        (MediaProbeError('ffprobe'), "I couldn't inspect this MP4 safely with FFprobe, so the explanation could not continue."),
        (MediaExtractionError('ffmpeg'), "I couldn't prepare media evidence safely with FFmpeg, so the explanation could not continue."),
        (AnalysisTimeoutError('timeout'), 'Claude took too long to analyze this video, so no explanation was posted. Please try again.'),
        (AnalysisBudgetError('budget'), "I couldn't fit this video evidence within the safe Claude request budget, so no explanation was posted. Please try a shorter or simpler clip in this thread."),
        (AnalysisProviderError('provider'), "Claude couldn't analyze this video successfully, so no explanation was posted. Please try again."),
        (AnalysisInvalidResponseError('invalid'), 'Claude returned an invalid explanation format, so no explanation was posted. Please try again.'),
    ]

    for exc, expected in cases:
        assert failure_message_for_exception(exc) == expected


def test_build_analysis_request_large_frame_fixture_stays_within_budget(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(
        tmp_path,
        name='large-frame-budget',
        with_audio=True,
        duration_seconds=2,
        size='1920x1080',
    )
    prepared = prepare_media_evidence(
        byte_stream=[fixture.read_bytes()],
        request_id='large-frame-budget',
        untrusted_filename='large-frame-budget.mp4',
        temp_root=tmp_path / 'workspaces',
        transcriber=FakeTranscriber(text='Narration.', timestamps_available=True),
    )

    request = build_analysis_request(prepared)
    envelope = build_prompt_envelope(request)

    assert request.frames
    assert all(frame.image_media_type == 'image/jpeg' for frame in request.frames)
    assert sum(len(frame.image_base64 or '') for frame in request.frames) <= MAX_TOTAL_IMAGE_BASE64_CHARS
    assert len(envelope.user_prompt) <= MAX_USER_PROMPT_CHARS
    assert 'image_base64' not in envelope.user_prompt
    prepared.workspace.cleanup(state='success')


def test_explanation_budget_overflow_posts_safe_failure_and_cleans_workspace(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='budget-overflow', with_audio=True, duration_seconds=1)
    temp_root = tmp_path / 'work'
    adapter = FakeAdapter(fixture.read_bytes())
    client = FakeSlackClient()
    analyzer = BudgetCheckingAnalyzer()
    oversized_transcript = 'a' * 25000
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger('tests.explanation.budget'),
        temp_root=temp_root,
        transcriber=FakeTranscriber(text=oversized_transcript, timestamps_available=True),
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert analyzer.calls
    assert client.calls[0]['text'] == (
        "I couldn't fit this video evidence within the safe Claude request budget, so no explanation was posted. "
        'Please try a shorter or simpler clip in this thread.'
    )
    assert temp_root.exists() is True
    assert list(temp_root.iterdir()) == []


def test_explanation_provider_rejection_posts_safe_failure_and_cleans_workspace(tmp_path: Path) -> None:
    fixture = build_mp4_fixture(tmp_path, name='provider-rejection', with_audio=True, duration_seconds=1)
    temp_root = tmp_path / 'work'
    adapter = FakeAdapter(fixture.read_bytes())
    client = FakeSlackClient()
    analyzer = ProviderRejectingAnalyzer()
    orchestrator = ExplanationOrchestrator(
        file_adapter_factory=lambda _: adapter,
        analyzer_factory=lambda: analyzer,
        executor=ImmediateExecutor(),
        logger=logging.getLogger('tests.explanation.provider_rejection'),
        temp_root=temp_root,
        transcriber=FakeTranscriber(text='Narration.', timestamps_available=True),
    )

    orchestrator.enqueue(client=client, session=make_session())

    assert analyzer.calls
    assert client.calls[0]['text'] == "Claude couldn't analyze this video successfully, so no explanation was posted. Please try again."
    assert temp_root.exists() is True
    assert list(temp_root.iterdir()) == []
