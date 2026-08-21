from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse

from slack_video_assistant.logging_utils import redact_sensitive


class SlackAdapterError(RuntimeError):
    """Raised when Slack metadata or download operations fail safely."""


class SlackWebClient(Protocol):
    def files_info(self, *, file: str) -> Mapping[str, Any]: ...


class DownloadResponse(Protocol):
    def iter_bytes(self, chunk_size: int = 65536) -> Any: ...


class SlackFileDownloader(Protocol):
    def stream(self, *, url: str, headers: Mapping[str, str]) -> DownloadResponse: ...


@dataclass(frozen=True)
class SlackFileRecord:
    file_id: str
    name: str
    mimetype: str
    filetype: str
    url_private_download: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class DownloadedSlackFile:
    file_id: str
    workspace_dir: Path
    local_path: Path
    byte_count: int


class SlackFileAdapter:
    def __init__(
        self,
        *,
        bot_token: str,
        client: SlackWebClient,
        downloader: SlackFileDownloader,
        max_bytes: int,
        temp_root: Path | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._client = client
        self._downloader = downloader
        self._max_bytes = max_bytes
        self._temp_root = temp_root

    def get_file_record(self, file_id: str) -> SlackFileRecord:
        try:
            response = self._client.files_info(file=file_id)
            raw_file = response["file"]
            url_private_download = str(raw_file["url_private_download"])
            self._validate_download_url(url_private_download)
            return SlackFileRecord(
                file_id=str(raw_file.get("id", file_id)),
                name=str(raw_file.get("name", "")),
                mimetype=str(raw_file.get("mimetype", "")),
                filetype=str(raw_file.get("filetype", "")),
                url_private_download=url_private_download,
                raw=raw_file,
            )
        except SlackAdapterError:
            raise
        except Exception as exc:
            raise SlackAdapterError(
                f"Slack file metadata lookup failed: {redact_sensitive(exc)}"
            ) from exc

    def download_file(self, file_id: str) -> DownloadedSlackFile:
        record = self.get_file_record(file_id)
        workspace_dir = Path(
            tempfile.mkdtemp(prefix="slack-video-assistant-", dir=self._temp_root)
        )
        local_path = workspace_dir / "input.mp4"
        bytes_written = 0

        try:
            response = self._downloader.stream(
                url=record.url_private_download,
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
            with local_path.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=65536):
                    if not chunk:
                        continue
                    bytes_written += len(chunk)
                    if bytes_written > self._max_bytes:
                        raise SlackAdapterError("Slack file exceeds the configured byte limit.")
                    handle.write(chunk)

            return DownloadedSlackFile(
                file_id=record.file_id,
                workspace_dir=workspace_dir,
                local_path=local_path,
                byte_count=bytes_written,
            )
        except SlackAdapterError:
            self._cleanup_workspace(workspace_dir)
            raise
        except Exception as exc:
            self._cleanup_workspace(workspace_dir)
            raise SlackAdapterError(
                f"Slack file download failed: {redact_sensitive(exc)}"
            ) from exc

    def iter_download_bytes(self, file_record: SlackFileRecord) -> Any:
        try:
            response = self._downloader.stream(
                url=file_record.url_private_download,
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
            return response.iter_bytes(chunk_size=65536)
        except Exception as exc:
            raise SlackAdapterError(f"Slack file download failed: {redact_sensitive(exc)}") from exc

    def _validate_download_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            raise SlackAdapterError("Slack file metadata contained an invalid download reference.")
        if host != "slack.com" and not host.endswith(".slack.com"):
            raise SlackAdapterError("Slack file metadata contained an untrusted download host.")

    def _cleanup_workspace(self, workspace_dir: Path) -> None:
        shutil.rmtree(workspace_dir, ignore_errors=True)


def is_supported_mp4(file_record: SlackFileRecord) -> bool:
    if file_record.filetype.lower() == "mp4":
        return True
    if file_record.mimetype.lower() == "video/mp4":
        return True
    return file_record.name.lower().endswith(".mp4")
