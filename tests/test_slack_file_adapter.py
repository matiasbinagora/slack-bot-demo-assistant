from __future__ import annotations

from pathlib import Path

import pytest

from slack_video_assistant.slack_file_adapter import SlackAdapterError, SlackFileAdapter


class FakeSlackClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def files_info(self, *, file: str):
        self.calls.append(file)
        return self.response


class FakeDownloadResponse:
    def __init__(self, chunks):
        self._chunks = chunks

    def iter_bytes(self, chunk_size: int = 65536):
        del chunk_size
        yield from self._chunks


class FakeDownloader:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def stream(self, *, url: str, headers):
        self.calls.append({"url": url, "headers": dict(headers)})
        if self.error is not None:
            raise self.error
        return self.response


def make_response(url: str = "https://files.slack.com/files-pri/T1-F1/download"):
    return {
        "file": {
            "id": "F1",
            "name": "../../secret.mp4",
            "mimetype": "video/mp4",
            "filetype": "mp4",
            "url_private_download": url,
        }
    }


def test_download_file_uses_authenticated_stream_and_controlled_output_path(tmp_path: Path) -> None:
    downloader = FakeDownloader(response=FakeDownloadResponse([b"abc", b"def"]))
    adapter = SlackFileAdapter(
        bot_token="xoxb-secret-token",
        client=FakeSlackClient(make_response()),
        downloader=downloader,
        max_bytes=10,
        temp_root=tmp_path,
    )

    downloaded = adapter.download_file("F1")

    assert downloaded.byte_count == 6
    assert downloaded.local_path.name == "input.mp4"
    assert downloaded.local_path.read_bytes() == b"abcdef"
    assert downloaded.workspace_dir.parent == tmp_path
    assert downloader.calls == [
        {
            "url": "https://files.slack.com/files-pri/T1-F1/download",
            "headers": {"Authorization": "Bearer xoxb-secret-token"},
        }
    ]


def test_download_file_rejects_untrusted_download_host(tmp_path: Path) -> None:
    adapter = SlackFileAdapter(
        bot_token="xoxb-secret-token",
        client=FakeSlackClient(make_response(url="https://evil.example/video.mp4")),
        downloader=FakeDownloader(response=FakeDownloadResponse([b"abc"])),
        max_bytes=10,
        temp_root=tmp_path,
    )

    with pytest.raises(SlackAdapterError) as exc_info:
        adapter.download_file("F1")

    assert str(exc_info.value) == "Slack file metadata contained an untrusted download host."
    assert list(tmp_path.iterdir()) == []


def test_download_file_enforces_byte_limit_and_cleans_partial_files(tmp_path: Path) -> None:
    downloader = FakeDownloader(response=FakeDownloadResponse([b"1234", b"5678"]))
    adapter = SlackFileAdapter(
        bot_token="xoxb-secret-token",
        client=FakeSlackClient(make_response()),
        downloader=downloader,
        max_bytes=6,
        temp_root=tmp_path,
    )

    with pytest.raises(SlackAdapterError) as exc_info:
        adapter.download_file("F1")

    assert str(exc_info.value) == "Slack file exceeds the configured byte limit."
    assert list(tmp_path.iterdir()) == []


def test_download_file_redacts_failure_details_and_cleans_workspace(tmp_path: Path) -> None:
    adapter = SlackFileAdapter(
        bot_token="xoxb-secret-token",
        client=FakeSlackClient(make_response()),
        downloader=FakeDownloader(
            error=RuntimeError(
                "download failed for https://files.slack.com/private with xoxb-secret-token"
            )
        ),
        max_bytes=10,
        temp_root=tmp_path,
    )

    with pytest.raises(SlackAdapterError) as exc_info:
        adapter.download_file("F1")

    message = str(exc_info.value)
    assert "Slack file download failed:" in message
    assert "xoxb-secret-token" not in message
    assert "https://files.slack.com/private" not in message
    assert "[REDACTED_TOKEN]" in message
    assert "[REDACTED_URL]" in message
    assert list(tmp_path.iterdir()) == []
