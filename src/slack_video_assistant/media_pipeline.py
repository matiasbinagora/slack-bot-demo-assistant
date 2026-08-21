from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from slack_video_assistant.logging_utils import redact_sensitive


DEFAULT_MAX_VIDEO_BYTES = 104857600
DEFAULT_MAX_VIDEO_DURATION_SECONDS = 300.0
DEFAULT_FRAME_COUNT = 3
MAX_FRAME_EDGE_PIXELS = 512
FRAME_JPEG_QUALITY = 8
FRAME_END_MARGIN_SECONDS = 0.25


class MediaPipelineError(RuntimeError):
    """Base safe error for the local media pipeline."""


class MediaValidationError(MediaPipelineError):
    """Raised when media validation fails."""


class MediaProbeError(MediaPipelineError):
    """Raised when FFprobe fails or returns unusable metadata."""


class MediaExtractionError(MediaPipelineError):
    """Raised when FFmpeg cannot extract required evidence."""


class EvidenceStatus(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int
    container_names: tuple[str, ...]
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool


@dataclass(frozen=True)
class ExtractedFrame:
    path: Path
    label: str
    timestamp_seconds: float | None


@dataclass(frozen=True)
class TranscriptionResult:
    transcript_text: str
    timestamps_available: bool


class AudioTranscriber(Protocol):
    def transcribe(self, *, audio_path: Path) -> TranscriptionResult: ...


@dataclass(frozen=True)
class AudioEvidence:
    status: EvidenceStatus
    detail: str
    audio_path: Path | None = None
    transcript_path: Path | None = None
    transcript_text: str | None = None
    timestamps_available: bool = False
    transcription_failed: bool = False


@dataclass(frozen=True)
class PreparedMediaEvidence:
    workspace: "MediaWorkspace"
    source_path: Path
    metadata: VideoMetadata
    frames: tuple[ExtractedFrame, ...]
    audio_evidence: AudioEvidence


@dataclass(frozen=True)
class CleanupResult:
    state: str
    attempted: bool
    succeeded: bool
    detail: str


class MediaWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @classmethod
    def create(cls, *, temp_root: Path | None = None, request_id: str | None = None) -> "MediaWorkspace":
        base_root = _prepare_temp_root(temp_root)
        prefix = f"slack-video-assistant-{_normalize_request_id(request_id)}-"
        try:
            root = Path(tempfile.mkdtemp(prefix=prefix, dir=base_root))
        except FileNotFoundError as exc:
            raise MediaValidationError(
                "The configured video temp directory is unavailable for analysis."
            ) from exc
        except PermissionError as exc:
            raise MediaValidationError(
                "The configured video temp directory is unavailable for analysis."
            ) from exc
        os.chmod(root, 0o700)
        return cls(root)

    @property
    def source_path(self) -> Path:
        return self.controlled_path("source.mp4")

    @property
    def frames_dir(self) -> Path:
        return self.ensure_dir("frames")

    @property
    def audio_dir(self) -> Path:
        return self.ensure_dir("audio")

    @property
    def transcript_dir(self) -> Path:
        return self.ensure_dir("transcript")

    def ensure_dir(self, relative_path: str) -> Path:
        path = self.controlled_path(relative_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def controlled_path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise MediaValidationError("Media workspace rejected an unsafe output path.")
        return candidate

    def cleanup(self, *, state: str, logger: logging.Logger | None = None) -> CleanupResult:
        try:
            shutil.rmtree(self.root)
            return CleanupResult(
                state=state,
                attempted=True,
                succeeded=True,
                detail=f"Workspace cleanup completed for terminal state `{state}`.",
            )
        except FileNotFoundError:
            return CleanupResult(
                state=state,
                attempted=True,
                succeeded=True,
                detail=f"Workspace cleanup was already complete for terminal state `{state}`.",
            )
        except Exception as exc:
            detail = (
                f"Workspace cleanup failed for terminal state `{state}`: {redact_sensitive(exc)}"
            )
            if logger is not None:
                logger.warning(detail)
            return CleanupResult(state=state, attempted=True, succeeded=False, detail=detail)


def prepare_media_evidence(
    *,
    byte_stream: Iterable[bytes],
    request_id: str,
    untrusted_filename: str,
    temp_root: Path | None = None,
    max_bytes: int = DEFAULT_MAX_VIDEO_BYTES,
    max_duration_seconds: float = DEFAULT_MAX_VIDEO_DURATION_SECONDS,
    frame_count: int = DEFAULT_FRAME_COUNT,
    ffprobe_command: str = "ffprobe",
    ffmpeg_command: str = "ffmpeg",
    transcriber: AudioTranscriber | None = None,
) -> PreparedMediaEvidence:
    del untrusted_filename
    workspace = MediaWorkspace.create(temp_root=temp_root, request_id=request_id)
    try:
        source_path = workspace.source_path
        write_bounded_stream_to_path(byte_stream=byte_stream, destination=source_path, max_bytes=max_bytes)
        metadata = probe_video(
            source_path,
            ffprobe_command=ffprobe_command,
            max_duration_seconds=max_duration_seconds,
        )
        frames = extract_frames(
            source_path,
            workspace=workspace,
            duration_seconds=metadata.duration_seconds,
            frame_count=frame_count,
            ffmpeg_command=ffmpeg_command,
        )
        audio_evidence = build_audio_evidence(
            source_path,
            workspace=workspace,
            metadata=metadata,
            ffmpeg_command=ffmpeg_command,
            transcriber=transcriber,
        )
        return PreparedMediaEvidence(
            workspace=workspace,
            source_path=source_path,
            metadata=metadata,
            frames=frames,
            audio_evidence=audio_evidence,
        )
    except Exception:
        workspace.cleanup(state="failure")
        raise


def write_bounded_stream_to_path(
    *, byte_stream: Iterable[bytes], destination: Path, max_bytes: int
) -> int:
    if max_bytes <= 0:
        raise MediaValidationError("Media byte limit must be greater than zero.")

    byte_count = 0
    with destination.open("wb") as handle:
        for chunk in byte_stream:
            if not chunk:
                continue
            byte_count += len(chunk)
            if byte_count > max_bytes:
                raise MediaValidationError(
                    "This MP4 exceeds the 100 MB upload limit for the MVP."
                )
            handle.write(chunk)
    return byte_count


def probe_video(
    source_path: Path,
    *,
    ffprobe_command: str = "ffprobe",
    max_duration_seconds: float = DEFAULT_MAX_VIDEO_DURATION_SECONDS,
) -> VideoMetadata:
    _validate_duration_limit(max_duration_seconds)
    payload = _run_ffprobe(source_path, ffprobe_command=ffprobe_command)
    format_payload = payload.get("format")
    if not isinstance(format_payload, Mapping):
        raise MediaProbeError("FFprobe did not return media format metadata.")

    container_names = tuple(
        item.strip().lower()
        for item in str(format_payload.get("format_name", "")).split(",")
        if item.strip()
    )
    if not _is_valid_mp4_container(container_names, format_payload):
        raise MediaValidationError(
            "I can only analyze valid MP4 uploads for this MVP."
        )

    try:
        duration_seconds = float(format_payload["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaProbeError("FFprobe did not return a usable media duration.") from exc

    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise MediaValidationError("This MP4 is missing a usable duration for analysis.")
    if duration_seconds > max_duration_seconds:
        raise MediaValidationError(
            "This MP4 is longer than the 5 minute limit for the MVP."
        )

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise MediaProbeError("FFprobe did not return media stream metadata.")

    video_stream = next(
        (stream for stream in streams if isinstance(stream, Mapping) and stream.get("codec_type") == "video"),
        None,
    )
    if not isinstance(video_stream, Mapping):
        raise MediaValidationError("This upload does not contain a usable video stream.")

    width = _int_field(video_stream, "width", message="FFprobe did not return the video width.")
    height = _int_field(video_stream, "height", message="FFprobe did not return the video height.")
    audio_stream = next(
        (stream for stream in streams if isinstance(stream, Mapping) and stream.get("codec_type") == "audio"),
        None,
    )

    return VideoMetadata(
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        container_names=container_names,
        video_codec=_optional_string(video_stream.get("codec_name")),
        audio_codec=_optional_string(audio_stream.get("codec_name")) if isinstance(audio_stream, Mapping) else None,
        has_audio=isinstance(audio_stream, Mapping),
    )


def extract_frames(
    source_path: Path,
    *,
    workspace: MediaWorkspace,
    duration_seconds: float,
    frame_count: int = DEFAULT_FRAME_COUNT,
    ffmpeg_command: str = "ffmpeg",
) -> tuple[ExtractedFrame, ...]:
    if frame_count <= 0:
        raise MediaValidationError("Frame extraction requires at least one frame.")

    frame_timestamps = _select_frame_timestamps(duration_seconds=duration_seconds, frame_count=frame_count)
    extracted: list[ExtractedFrame] = []
    for index, timestamp_seconds in enumerate(frame_timestamps, start=1):
        output_path = workspace.controlled_path(f"frames/frame-{index:02d}.jpg")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _run_ffmpeg(
            [
                ffmpeg_command,
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{timestamp_seconds:.3f}",
                "-i",
                str(source_path),
                "-vf",
                f"scale={MAX_FRAME_EDGE_PIXELS}:{MAX_FRAME_EDGE_PIXELS}:force_original_aspect_ratio=decrease",
                "-frames:v",
                "1",
                "-q:v",
                str(FRAME_JPEG_QUALITY),
                str(output_path),
            ],
            failure_message="FFmpeg could not extract a representative frame.",
        )
        extracted.append(
            ExtractedFrame(
                path=output_path,
                label=f"frame-{index:02d}",
                timestamp_seconds=timestamp_seconds,
            )
        )

    return tuple(extracted)


def build_audio_evidence(
    source_path: Path,
    *,
    workspace: MediaWorkspace,
    metadata: VideoMetadata,
    ffmpeg_command: str = "ffmpeg",
    transcriber: AudioTranscriber | None = None,
) -> AudioEvidence:
    if not metadata.has_audio:
        return AudioEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            detail="This MP4 has no audio track, so transcript evidence is unavailable.",
        )

    audio_path = workspace.controlled_path("audio/source.wav")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run_ffmpeg(
            [
                ffmpeg_command,
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(audio_path),
            ],
            failure_message="FFmpeg could not extract audio evidence.",
        )
    except MediaExtractionError:
        return AudioEvidence(
            status=EvidenceStatus.DEGRADED,
            detail="Audio extraction was unavailable, so analysis must continue with visual evidence only.",
        )

    if transcriber is None:
        return AudioEvidence(
            status=EvidenceStatus.DEGRADED,
            detail="Audio was extracted, but local transcription is unavailable in this environment.",
            audio_path=audio_path,
        )

    try:
        transcription = transcriber.transcribe(audio_path=audio_path)
    except Exception:
        return AudioEvidence(
            status=EvidenceStatus.DEGRADED,
            detail="Audio was extracted, but transcription failed safely and no transcript was retained.",
            audio_path=audio_path,
            transcription_failed=True,
        )

    transcript_path = workspace.controlled_path("transcript/transcript.txt")
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(transcription.transcript_text, encoding="utf-8")

    return AudioEvidence(
        status=(
            EvidenceStatus.AVAILABLE
            if transcription.timestamps_available
            else EvidenceStatus.DEGRADED
        ),
        detail=(
            "Audio transcript and timestamps are available."
            if transcription.timestamps_available
            else "Audio transcript is available, but reliable timestamps are unavailable."
        ),
        audio_path=audio_path,
        transcript_path=transcript_path,
        transcript_text=transcription.transcript_text,
        timestamps_available=transcription.timestamps_available,
    )


def _run_ffprobe(source_path: Path, *, ffprobe_command: str) -> Mapping[str, object]:
    try:
        result = subprocess.run(
            [
                ffprobe_command,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-print_format",
                "json",
                str(source_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaProbeError("FFprobe is unavailable in this environment.") from exc
    except Exception as exc:
        raise MediaProbeError(
            f"FFprobe failed before probing media: {redact_sensitive(exc)}"
        ) from exc

    if result.returncode != 0:
        raise MediaProbeError("FFprobe could not validate this upload safely.")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError("FFprobe returned malformed JSON output.") from exc
    if not isinstance(payload, Mapping):
        raise MediaProbeError("FFprobe returned an unexpected metadata structure.")
    return payload


def _run_ffmpeg(command: Sequence[str], *, failure_message: str) -> None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise MediaExtractionError("FFmpeg is unavailable in this environment.") from exc
    except Exception as exc:
        raise MediaExtractionError(f"{failure_message} {redact_sensitive(exc)}") from exc

    if result.returncode != 0:
        raise MediaExtractionError(failure_message)


def _is_valid_mp4_container(
    container_names: Sequence[str], format_payload: Mapping[str, object]
) -> bool:
    if "mp4" in container_names:
        return True

    tags = format_payload.get("tags")
    if isinstance(tags, Mapping):
        major_brand = str(tags.get("major_brand", "")).strip().lower()
        if major_brand in {"isom", "iso2", "mp41", "mp42", "avc1"}:
            return True
    return False


def _int_field(stream: Mapping[str, object], key: str, *, message: str) -> int:
    value = stream.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MediaProbeError(message) from exc
    if parsed <= 0:
        raise MediaProbeError(message)
    return parsed


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate_duration_limit(max_duration_seconds: float) -> None:
    if not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0:
        raise MediaValidationError("The configured video duration limit is invalid.")


def _prepare_temp_root(temp_root: Path | None) -> Path | None:
    if temp_root is None:
        return None

    try:
        temp_root.mkdir(parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise MediaValidationError(
            "The configured video temp directory is unavailable for analysis."
        ) from exc
    except OSError as exc:
        raise MediaValidationError(
            "The configured video temp directory is unavailable for analysis."
        ) from exc

    try:
        return temp_root.resolve()
    except OSError as exc:
        raise MediaValidationError(
            "The configured video temp directory is unavailable for analysis."
        ) from exc


def _select_frame_timestamps(*, duration_seconds: float, frame_count: int) -> tuple[float, ...]:
    if duration_seconds <= 0:
        return (0.0,)
    if frame_count == 1:
        return (0.0,)

    max_timestamp = max(duration_seconds - FRAME_END_MARGIN_SECONDS, 0.0)
    if max_timestamp == 0.0:
        return (0.0,)

    step = max_timestamp / (frame_count - 1)
    timestamps = {round(step * index, 3) for index in range(frame_count)}
    return tuple(sorted(timestamps))


def _normalize_request_id(request_id: str | None) -> str:
    raw = (request_id or str(uuid.uuid4())).strip().lower()
    filtered = "".join(char if char.isalnum() else "-" for char in raw)
    normalized = "-".join(part for part in filtered.split("-") if part)
    return normalized[:32] or "request"
