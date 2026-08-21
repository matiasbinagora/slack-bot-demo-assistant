from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from slack_video_assistant.media_pipeline import (
    CleanupResult,
    DEFAULT_MAX_VIDEO_DURATION_SECONDS,
    EvidenceStatus,
    MediaExtractionError,
    MediaProbeError,
    MediaValidationError,
    MediaWorkspace,
    TranscriptionResult,
    VideoMetadata,
    _optional_string,
    build_audio_evidence,
    extract_frames,
    prepare_media_evidence,
    probe_video,
)


class FakeTranscriber:
    def __init__(self, *, text: str = "Detected narration.", timestamps_available: bool) -> None:
        self.text = text
        self.timestamps_available = timestamps_available
        self.calls: list[Path] = []

    def transcribe(self, *, audio_path: Path) -> TranscriptionResult:
        self.calls.append(audio_path)
        return TranscriptionResult(
            transcript_text=self.text,
            timestamps_available=self.timestamps_available,
        )


class ExplodingTranscriber:
    def transcribe(self, *, audio_path: Path) -> TranscriptionResult:
        raise RuntimeError(f"transcriber failed for {audio_path}")


def test_prepare_media_evidence_accepts_valid_mp4_and_uses_controlled_paths(tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="valid-audio", with_audio=True, duration_seconds=2)

    prepared = prepare_media_evidence(
        byte_stream=[source_fixture.read_bytes()],
        request_id="Request 01",
        untrusted_filename="../../private/clip.mp4",
        temp_root=tmp_path,
    )

    assert prepared.source_path.name == "source.mp4"
    assert prepared.source_path.parent == prepared.workspace.root
    assert prepared.workspace.root.parent == tmp_path
    assert all(frame.path.parent == prepared.workspace.frames_dir for frame in prepared.frames)
    assert prepared.metadata.duration_seconds <= DEFAULT_MAX_VIDEO_DURATION_SECONDS
    assert prepared.metadata.has_audio is True
    assert prepared.audio_evidence.status is EvidenceStatus.DEGRADED
    assert prepared.audio_evidence.audio_path == prepared.workspace.controlled_path("audio/source.wav")
    assert prepared.audio_evidence.transcript_path is None
    cleanup = prepared.workspace.cleanup(state="success")
    assert cleanup.succeeded is True
    assert prepared.workspace.root.exists() is False


def test_prepare_media_evidence_rejects_non_mp4_content_even_with_mp4_name(tmp_path: Path) -> None:
    workspaces_root = tmp_path / "workspaces"
    workspaces_root.mkdir()

    with pytest.raises(MediaProbeError) as exc_info:
        prepare_media_evidence(
            byte_stream=[b"not an mp4"],
            request_id="invalid-format",
            untrusted_filename="looks-like-video.mp4",
            temp_root=workspaces_root,
        )

    assert "FFprobe could not validate this upload safely." in str(exc_info.value)
    assert list(workspaces_root.iterdir()) == []


def test_prepare_media_evidence_rejects_stream_that_exceeds_byte_limit(tmp_path: Path) -> None:
    workspaces_root = tmp_path / "workspaces"
    workspaces_root.mkdir()

    with pytest.raises(MediaValidationError) as exc_info:
        prepare_media_evidence(
            byte_stream=[b"1234", b"5678"],
            request_id="too-large",
            untrusted_filename="clip.mp4",
            temp_root=workspaces_root,
            max_bytes=6,
        )

    assert str(exc_info.value) == "This MP4 exceeds the 100 MB upload limit for the MVP."
    assert list(workspaces_root.iterdir()) == []


def test_probe_video_rejects_fixture_longer_than_five_minutes(tmp_path: Path) -> None:
    long_fixture = build_mp4_fixture(
        tmp_path,
        name="over-duration",
        with_audio=False,
        duration_seconds=301,
        size="16x16",
        fps=1,
    )

    with pytest.raises(MediaValidationError) as exc_info:
        probe_video(long_fixture)

    assert str(exc_info.value) == "This MP4 is longer than the 5 minute limit for the MVP."


def test_probe_video_rejects_non_finite_duration_metadata(monkeypatch, tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="non-finite-duration", with_audio=False, duration_seconds=1)

    monkeypatch.setattr(
        "slack_video_assistant.media_pipeline._run_ffprobe",
        lambda source_path, ffprobe_command: {
            "format": {"format_name": "mp4", "duration": "nan", "tags": {"major_brand": "isom"}},
            "streams": [
                {"codec_type": "video", "width": 32, "height": 32, "codec_name": "h264"},
            ],
        },
    )

    with pytest.raises(MediaValidationError) as exc_info:
        probe_video(source_fixture)

    assert str(exc_info.value) == "This MP4 is missing a usable duration for analysis."


def test_workspace_rejects_path_traversal_attempts(tmp_path: Path) -> None:
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id="safe")

    with pytest.raises(MediaValidationError) as exc_info:
        workspace.controlled_path("../escape.txt")

    assert str(exc_info.value) == "Media workspace rejected an unsafe output path."
    workspace.cleanup(state="validation_failure")


def test_extract_frames_reports_ffmpeg_failure_safely(tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="valid-no-audio", with_audio=False, duration_seconds=1)
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id="ffmpeg-fail")

    with pytest.raises(MediaExtractionError) as exc_info:
        extract_frames(
            source_fixture,
            workspace=workspace,
            duration_seconds=1.0,
            ffmpeg_command="ffmpeg-does-not-exist",
        )

    assert str(exc_info.value) == "FFmpeg is unavailable in this environment."
    workspace.cleanup(state="provider_failure")


def test_extract_frames_hides_raw_ffmpeg_diagnostics(monkeypatch, tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="ffmpeg-diagnostics", with_audio=False, duration_seconds=1)
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id="ffmpeg-diagnostics")

    def fake_run(command, capture_output, text, check):
        return SimpleNamespace(
            returncode=1,
            stderr="codec=h264 width=1920 private_url=https://files.slack.com/private",
            stdout="",
        )

    monkeypatch.setattr("slack_video_assistant.media_pipeline.subprocess.run", fake_run)

    with pytest.raises(MediaExtractionError) as exc_info:
        extract_frames(source_fixture, workspace=workspace, duration_seconds=1.0)

    assert str(exc_info.value) == "FFmpeg could not extract a representative frame."
    workspace.cleanup(state="provider_failure")


def test_prepare_media_evidence_cleans_workspace_after_frame_extraction_failure(tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="valid-audio-failure", with_audio=True, duration_seconds=2)
    workspaces_root = tmp_path / "workspaces"
    workspaces_root.mkdir()

    with pytest.raises(MediaExtractionError) as exc_info:
        prepare_media_evidence(
            byte_stream=[source_fixture.read_bytes()],
            request_id="frame-failure",
            untrusted_filename="clip.mp4",
            temp_root=workspaces_root,
            ffmpeg_command="ffmpeg-does-not-exist",
        )

    assert str(exc_info.value) == "FFmpeg is unavailable in this environment."
    assert list(workspaces_root.iterdir()) == []


def test_build_audio_evidence_marks_missing_audio_as_unavailable(tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="valid-no-audio", with_audio=False, duration_seconds=1)
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id="no-audio")

    evidence = build_audio_evidence(
        source_fixture,
        workspace=workspace,
        metadata=VideoMetadata(
            duration_seconds=1.0,
            width=32,
            height=32,
            container_names=("mp4",),
            video_codec="h264",
            audio_codec=None,
            has_audio=False,
        ),
    )

    assert evidence.status is EvidenceStatus.UNAVAILABLE
    assert evidence.audio_path is None
    assert evidence.timestamps_available is False
    workspace.cleanup(state="success")


def test_build_audio_evidence_degrades_when_transcription_timestamps_are_unavailable(tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="valid-audio", with_audio=True, duration_seconds=2)
    metadata = probe_video(source_fixture)
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id="transcript-degraded")
    transcriber = FakeTranscriber(timestamps_available=False)

    evidence = build_audio_evidence(
        source_fixture,
        workspace=workspace,
        metadata=metadata,
        transcriber=transcriber,
    )

    assert evidence.status is EvidenceStatus.DEGRADED
    assert evidence.audio_path is not None
    assert evidence.transcript_path is not None
    assert evidence.transcript_path.read_text(encoding="utf-8") == "Detected narration."
    assert evidence.timestamps_available is False
    assert transcriber.calls == [evidence.audio_path]
    workspace.cleanup(state="success")


def test_build_audio_evidence_handles_transcriber_failure_without_retaining_transcript(tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="valid-audio", with_audio=True, duration_seconds=2)
    metadata = probe_video(source_fixture)
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id="transcript-failure")

    evidence = build_audio_evidence(
        source_fixture,
        workspace=workspace,
        metadata=metadata,
        transcriber=ExplodingTranscriber(),
    )

    assert evidence.status is EvidenceStatus.DEGRADED
    assert evidence.transcript_path is None
    assert evidence.audio_path is not None
    workspace.cleanup(state="provider_failure")


@pytest.mark.parametrize(
    ("state", "expected_phrase"),
    [
        ("success", "completed"),
        ("validation_failure", "completed"),
        ("provider_failure", "completed"),
        ("cancelled", "completed"),
        ("timeout", "completed"),
    ],
)
def test_workspace_cleanup_runs_for_all_terminal_states(
    tmp_path: Path, state: str, expected_phrase: str
) -> None:
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id=state)
    workspace.controlled_path("frames/placeholder.txt").parent.mkdir(parents=True, exist_ok=True)
    workspace.controlled_path("frames/placeholder.txt").write_text("frame", encoding="utf-8")

    result = workspace.cleanup(state=state)

    assert isinstance(result, CleanupResult)
    assert result.state == state
    assert result.succeeded is True
    assert expected_phrase in result.detail
    assert workspace.root.exists() is False


def test_workspace_cleanup_logs_failure_without_media_contents(monkeypatch, tmp_path: Path, caplog) -> None:
    workspace = MediaWorkspace.create(temp_root=tmp_path, request_id="cleanup-log")
    logger = logging.getLogger("tests.media_pipeline.cleanup")

    def fail_rmtree(path: Path) -> None:
        raise RuntimeError(f"could not remove {path}")

    monkeypatch.setattr("slack_video_assistant.media_pipeline.shutil.rmtree", fail_rmtree)

    with caplog.at_level(logging.WARNING):
        result = workspace.cleanup(state="timeout", logger=logger)

    assert result.succeeded is False
    assert workspace.root.exists() is True
    assert str(workspace.root) not in caplog.text
    assert "[REDACTED_PATH]" in caplog.text


def build_mp4_fixture(
    directory: Path,
    *,
    name: str,
    with_audio: bool,
    duration_seconds: int,
    size: str = "32x32",
    fps: int = 5,
) -> Path:
    output_path = directory / f"{name}.mp4"
    command = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={size}:rate={fps}:duration={duration_seconds}",
    ]
    if with_audio:
        command.extend(["-f", "lavfi", "-i", f"sine=frequency=880:duration={duration_seconds}"])
    command.extend(
        [
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "35",
        ]
    )
    if with_audio:
        command.extend(["-c:a", "aac", "-shortest"])
    command.append(str(output_path))
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output_path


def test_probe_video_rejects_invalid_duration_limit(tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="invalid-limit", with_audio=False, duration_seconds=1)

    with pytest.raises(MediaValidationError) as exc_info:
        probe_video(source_fixture, max_duration_seconds=float("nan"))

    assert str(exc_info.value) == "The configured video duration limit is invalid."


def test_optional_string_keeps_missing_codecs_as_none() -> None:
    assert _optional_string(None) is None
    assert _optional_string("  ") is None
    assert _optional_string("aac") == "aac"


def test_probe_video_keeps_absent_audio_codec_as_none(monkeypatch, tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="missing-codec", with_audio=True, duration_seconds=1)

    monkeypatch.setattr(
        "slack_video_assistant.media_pipeline._run_ffprobe",
        lambda source_path, ffprobe_command: {
            "format": {"format_name": "mp4", "duration": "1.0", "tags": {"major_brand": "isom"}},
            "streams": [
                {"codec_type": "video", "width": 32, "height": 32, "codec_name": None},
                {"codec_type": "audio", "codec_name": None},
            ],
        },
    )

    metadata = probe_video(source_fixture)

    assert metadata.video_codec is None
    assert metadata.audio_codec is None
    assert metadata.has_audio is True


def test_run_ffprobe_hides_raw_diagnostics(monkeypatch, tmp_path: Path) -> None:
    source_fixture = build_mp4_fixture(tmp_path, name="ffprobe-diagnostics", with_audio=False, duration_seconds=1)

    def fake_run(command, capture_output, text, check):
        return SimpleNamespace(
            returncode=1,
            stderr="codec=h264 duration=999 url=https://files.slack.com/private",
            stdout="",
        )

    monkeypatch.setattr("slack_video_assistant.media_pipeline.subprocess.run", fake_run)

    with pytest.raises(MediaProbeError) as exc_info:
        probe_video(source_fixture)

    assert str(exc_info.value) == "FFprobe could not validate this upload safely."
