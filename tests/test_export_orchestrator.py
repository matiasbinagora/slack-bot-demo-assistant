from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest

from slack_video_assistant.export_orchestrator import ExportOrchestrator, ImmediateExecutor
from slack_video_assistant.session_store import ExportRequest, SessionKey
from slack_video_assistant.slack_file_adapter import SlackFileRecord


def build_mp4_fixture(
    directory: Path,
    *,
    name: str,
    with_audio: bool,
    duration_seconds: int,
    size: str = "160x90",
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
    command.extend(["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35"])
    if with_audio:
        command.extend(["-c:a", "aac", "-shortest"])
    command.append(str(output_path))
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output_path


class RecordingAdapter:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path
        self.record = SlackFileRecord(
            file_id="F1",
            name="clip.mp4",
            mimetype="video/mp4",
            filetype="mp4",
            url_private_download=_inert_download_url(),
            raw={},
        )

    def get_file_record(self, file_id: str) -> SlackFileRecord:
        assert file_id == "F1"
        return self.record

    def iter_download_bytes(self, file_record: SlackFileRecord):
        assert file_record is self.record
        yield self.fixture_path.read_bytes()


class RecordingSlackClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def files_upload_v2(self, **payload: Any) -> None:
        self.calls.append(("files_upload_v2", payload))

    def chat_postMessage(self, **payload: Any) -> None:
        self.calls.append(("chat_postMessage", payload))


class ExplodingUploadClient(RecordingSlackClient):
    def files_upload_v2(self, **payload: Any) -> None:
        raise RuntimeError(_runtime_redaction_input())


def _inert_download_url() -> str:
    return "https://example.invalid/download/F1"


def _runtime_redaction_input() -> str:
    token = "".join(("xoxb", "-", "test", "-", "value"))
    url = "".join(("https://", "example.invalid", "/private-export"))
    path = str(Path("/", "var", "tmp", "private-export.mp4"))
    return f"token={token} url={url} path={path}"


def make_request() -> ExportRequest:
    return ExportRequest(
        key=SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001"),
        file_id="F1",
        target_ratio="16:9",
    )


def test_export_orchestrator_publishes_validated_output_before_cleanup(tmp_path: Path, monkeypatch) -> None:
    fixture = build_mp4_fixture(tmp_path, name="success", with_audio=True, duration_seconds=1)
    call_order: list[str] = []
    client = RecordingSlackClient()

    def record_validation(*args: Any, **kwargs: Any):
        call_order.append("validate")
        from slack_video_assistant.media_pipeline import validate_exported_video as real_validate_exported_video

        return real_validate_exported_video(*args, **kwargs)

    def record_upload(**payload: Any) -> None:
        call_order.append("publish")
        RecordingSlackClient.files_upload_v2(client, **payload)

    def record_cleanup(self, *, state: str, logger=None):
        call_order.append("cleanup")
        return original_cleanup(self, state=state, logger=logger)

    from slack_video_assistant.media_pipeline import MediaWorkspace

    original_cleanup = MediaWorkspace.cleanup
    monkeypatch.setattr("slack_video_assistant.export_orchestrator.validate_exported_video", record_validation)
    monkeypatch.setattr(client, "files_upload_v2", record_upload)
    monkeypatch.setattr(MediaWorkspace, "cleanup", record_cleanup)

    orchestrator = ExportOrchestrator(
        file_adapter_factory=lambda _: RecordingAdapter(fixture),
        executor=ImmediateExecutor(),
        logger=logging.getLogger("tests.export_orchestrator.success"),
        temp_root=tmp_path / "work",
    )

    orchestrator.submit(client=client, request=make_request())

    assert call_order == ["validate", "publish", "cleanup"]
    upload_calls = [payload for name, payload in client.calls if name == "files_upload_v2"]
    assert len(upload_calls) == 1
    assert upload_calls[0]["channel"] == "C1"
    assert upload_calls[0]["thread_ts"] == "170.0001"
    assert "16:9" in upload_calls[0]["title"]
    assert not [payload for name, payload in client.calls if name == "chat_postMessage"]


def test_export_orchestrator_rejects_invalid_output_without_publication_and_cleans_up(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = build_mp4_fixture(tmp_path, name="invalid", with_audio=True, duration_seconds=1)
    client = RecordingSlackClient()
    cleanup_states: list[str] = []

    from slack_video_assistant.media_pipeline import MediaValidationError, MediaWorkspace

    def fail_validation(*args: Any, **kwargs: Any):
        raise MediaValidationError("The export validation failed safely.")

    def record_cleanup(self, *, state: str, logger=None):
        cleanup_states.append(state)
        return original_cleanup(self, state=state, logger=logger)

    original_cleanup = MediaWorkspace.cleanup
    monkeypatch.setattr("slack_video_assistant.export_orchestrator.validate_exported_video", fail_validation)
    monkeypatch.setattr(MediaWorkspace, "cleanup", record_cleanup)

    orchestrator = ExportOrchestrator(
        file_adapter_factory=lambda _: RecordingAdapter(fixture),
        executor=ImmediateExecutor(),
        logger=logging.getLogger("tests.export_orchestrator.invalid"),
        temp_root=tmp_path / "work",
    )

    orchestrator.submit(client=client, request=make_request())

    assert [name for name, _payload in client.calls] == ["chat_postMessage"]
    assert client.calls[0][1] == {
        "channel": "C1",
        "thread_ts": "170.0001",
        "text": "The export validation failed safely.",
    }
    assert cleanup_states == ["failure"]


def test_export_orchestrator_logs_redacted_upload_failure_and_attempts_cleanup(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    fixture = build_mp4_fixture(tmp_path, name="upload-failure", with_audio=True, duration_seconds=1)
    cleanup_states: list[str] = []
    client = ExplodingUploadClient()

    from slack_video_assistant.media_pipeline import MediaWorkspace

    def record_cleanup(self, *, state: str, logger=None):
        cleanup_states.append(state)
        return original_cleanup(self, state=state, logger=logger)

    original_cleanup = MediaWorkspace.cleanup
    monkeypatch.setattr(MediaWorkspace, "cleanup", record_cleanup)

    orchestrator = ExportOrchestrator(
        file_adapter_factory=lambda _: RecordingAdapter(fixture),
        executor=ImmediateExecutor(),
        logger=logging.getLogger("tests.export_orchestrator.upload_failure"),
        temp_root=tmp_path / "work",
    )

    with caplog.at_level(logging.ERROR, logger="tests.export_orchestrator.upload_failure"):
        orchestrator.submit(client=client, request=make_request())

    original_runtime_text = _runtime_redaction_input()
    original_runtime_path = str(Path("/", "var", "tmp", "private-export.mp4"))
    assert [name for name, _payload in client.calls] == ["chat_postMessage"]
    assert client.calls[0][1]["text"] == (
        "I couldn't publish the validated export in Slack, so no file was posted. Please try again in this thread."
    )
    assert cleanup_states == ["publish_failure"]
    assert original_runtime_text not in caplog.text
    assert "example.invalid/private-export" not in caplog.text
    assert original_runtime_path not in caplog.text
    assert "[REDACTED_TOKEN]" in caplog.text
    assert "[REDACTED_URL]" in caplog.text
    assert "[REDACTED_PATH]" in caplog.text
