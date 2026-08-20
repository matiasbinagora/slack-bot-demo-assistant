from __future__ import annotations

import logging
from typing import Any

from slack_video_assistant.session_store import (
    CanonicalCommand,
    SessionKey,
    SessionStatus,
    ThreadSessionStore,
)
from slack_video_assistant.slack_events import ProcessedEventStore, SlackEventHandler, register_slack_handlers
from slack_video_assistant.slack_file_adapter import SlackFileAdapter


class FakeSlackClient:
    def __init__(self, file_response: dict[str, Any]) -> None:
        self.file_response = file_response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def files_info(self, *, file: str) -> dict[str, Any]:
        self.calls.append(("files_info", {"file": file}))
        return self.file_response

    def chat_postMessage(self, **payload: Any) -> None:
        self.calls.append(("chat_postMessage", payload))


class ExplodingSlackClient(FakeSlackClient):
    def __init__(self) -> None:
        super().__init__({})

    def files_info(self, *, file: str) -> dict[str, Any]:
        raise RuntimeError(
            "token=xoxb-secret-token url=https://files.slack.com/private path=/tmp/private/video.mp4"
        )


class FakeDownloader:
    def stream(self, *, url: str, headers):
        raise AssertionError(f"download should not run in this task slice: {url} {headers}")


class FakeApp:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def event(self, name: str):
        def _register(handler):
            self.handlers[name] = handler
            return handler

        return _register


def make_handler() -> tuple[SlackEventHandler, ThreadSessionStore]:
    store = ThreadSessionStore()

    def _factory(client: Any) -> SlackFileAdapter:
        return SlackFileAdapter(
            bot_token="xoxb-secret-token",
            client=client,
            downloader=FakeDownloader(),
            max_bytes=1024,
        )

    return (
        SlackEventHandler(
            file_adapter_factory=_factory,
            session_store=store,
            processed_events=ProcessedEventStore(),
            logger=logging.getLogger("tests.slack_events"),
        ),
        store,
    )


def make_file_response(*, channel_id: str = "C1", thread_ts: str | None = "170.0001") -> dict[str, Any]:
    share_entry: dict[str, Any] = {"ts": "170.0000"}
    if thread_ts is not None:
        share_entry["thread_ts"] = thread_ts
    return {
        "file": {
            "id": "F1",
            "name": "clip.mp4",
            "mimetype": "video/mp4",
            "filetype": "mp4",
            "url_private_download": "https://files.slack.com/files-pri/T1-F1/download",
            "shares": {"public": {channel_id: [share_entry]}},
        }
    }


def test_file_shared_acknowledges_before_metadata_lookup_and_posts_thread_reply() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    order: list[str] = []

    handler.handle_file_shared(
        body={
            "event_id": "Ev1",
            "team_id": "T1",
            "event": {"type": "file_shared", "file_id": "F1"},
        },
        ack=lambda: order.append("ack"),
        client=client,
    )

    assert order == ["ack"]
    assert client.calls[0] == ("files_info", {"file": "F1"})
    assert client.calls[1] == (
        "chat_postMessage",
        {
            "channel": "C1",
            "thread_ts": "170.0001",
            "text": "I found your MP4. Reply with `explain` for a summary or `export` to start the export confirmation flow.",
        },
    )
    session = store.get(SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001"))
    assert session is not None
    assert session.status is SessionStatus.VIDEO_RECEIVED


def test_file_shared_without_thread_requests_thread_upload_and_creates_no_session() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response(thread_ts=None))

    handler.handle_file_shared(
        body={
            "event_id": "Ev1",
            "team_id": "T1",
            "event": {"type": "file_shared", "file_id": "F1"},
        },
        ack=lambda: None,
        client=client,
    )

    assert client.calls[-1] == (
        "chat_postMessage",
        {
            "channel": "C1",
            "text": "Please share the MP4 from inside a Slack thread so I can keep the workflow in one place.",
        },
    )
    assert store.get(SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")) is None


def test_file_shared_metadata_failure_posts_safe_thread_reply_and_redacts_logs(caplog) -> None:
    handler, store = make_handler()
    client = ExplodingSlackClient()

    with caplog.at_level(logging.ERROR):
        handler.handle_file_shared(
            body={
                "event_id": "Ev1",
                "team_id": "T1",
                "event": {
                    "type": "file_shared",
                    "file_id": "F1",
                    "channel": "C1",
                    "thread_ts": "170.0001",
                },
            },
            ack=lambda: None,
            client=client,
        )

    assert client.calls[-1] == (
        "chat_postMessage",
        {
            "channel": "C1",
            "thread_ts": "170.0001",
            "text": "I couldn't read this Slack upload safely. Please share the MP4 in this thread again.",
        },
    )
    assert "xoxb-secret-token" not in caplog.text
    assert "https://files.slack.com/private" not in caplog.text
    assert "/tmp/private/video.mp4" not in caplog.text
    assert "[REDACTED_TOKEN]" in caplog.text
    assert "[REDACTED_URL]" in caplog.text
    assert "[REDACTED_PATH]" in caplog.text
    assert store.get(SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")) is None


def test_file_shared_with_mismatched_payload_channel_requests_thread_retry_without_state() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response(channel_id="C2", thread_ts="170.0002"))

    handler.handle_file_shared(
        body={
            "event_id": "Ev1",
            "team_id": "T1",
            "event": {"type": "file_shared", "file_id": "F1", "channel": "C1"},
        },
        ack=lambda: None,
        client=client,
    )

    assert client.calls[-1] == (
        "chat_postMessage",
        {
            "channel": "C1",
            "text": "Please share the MP4 from inside a Slack thread so I can keep the workflow in one place.",
        },
    )
    assert store.get(SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0002")) is None


def test_file_shared_with_ambiguous_shares_does_not_guess_thread() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(
        {
            "file": {
                "id": "F1",
                "name": "clip.mp4",
                "mimetype": "video/mp4",
                "filetype": "mp4",
                "url_private_download": "https://files.slack.com/files-pri/T1-F1/download",
                "shares": {
                    "public": {
                        "C1": [{"ts": "170.0000", "thread_ts": "170.0001"}],
                        "C2": [{"ts": "180.0000", "thread_ts": "180.0001"}],
                    }
                },
            }
        }
    )

    handler.handle_file_shared(
        body={
            "event_id": "Ev1",
            "team_id": "T1",
            "event": {"type": "file_shared", "file_id": "F1"},
        },
        ack=lambda: None,
        client=client,
    )

    assert [call for call in client.calls if call[0] == "chat_postMessage"] == []
    assert store.get(SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")) is None
    assert store.get(SessionKey(team_id="T1", channel_id="C2", thread_ts="180.0001")) is None


def test_file_shared_with_multiple_threads_in_same_channel_requests_thread_retry() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(
        {
            "file": {
                "id": "F1",
                "name": "clip.mp4",
                "mimetype": "video/mp4",
                "filetype": "mp4",
                "url_private_download": "https://files.slack.com/files-pri/T1-F1/download",
                "shares": {
                    "public": {
                        "C1": [
                            {"ts": "170.0000", "thread_ts": "170.0001"},
                            {"ts": "171.0000", "thread_ts": "171.0001"},
                        ]
                    }
                },
            }
        }
    )

    handler.handle_file_shared(
        body={
            "event_id": "Ev1",
            "team_id": "T1",
            "event": {"type": "file_shared", "file_id": "F1"},
        },
        ack=lambda: None,
        client=client,
    )

    assert client.calls[-1] == (
        "chat_postMessage",
        {
            "channel": "C1",
            "text": "Please share the MP4 from inside a Slack thread so I can keep the workflow in one place.",
        },
    )
    assert store.get(SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")) is None
    assert store.get(SessionKey(team_id="T1", channel_id="C1", thread_ts="171.0001")) is None


def test_message_commands_transition_state_and_handle_duplicates_safely() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev2",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev3",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev4",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "confirm"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev5",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "confirm"},
        },
        ack=lambda: None,
        client=client,
    )

    assert [payload[1]["text"] for payload in client.calls if payload[0] == "chat_postMessage"] == [
        "Export request noted. Reply with `confirm` to continue or `cancel` to stop.",
        "An export confirmation is already pending for this thread.",
        "Confirmation recorded. This task slice stops before FFmpeg export work starts.",
        "There is no pending export to confirm in this thread.",
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CONFIRMATION_CONSUMED


def test_message_requires_real_thread_context_and_ignores_root_messages() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev2",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "ts": "170.0002", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev3",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )

    assert [call for call in client.calls if call[0] == "chat_postMessage"] == []
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.VIDEO_RECEIVED


def test_retried_event_and_bot_message_do_not_duplicate_effects() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    body = {
        "event_id": "Ev2",
        "team_id": "T1",
        "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "explain"},
    }
    handler.handle_message(body=body, ack=lambda: None, client=client)
    handler.handle_message(body=body, ack=lambda: None, client=client)
    handler.handle_message(
        body={
            "event_id": "Ev3",
            "team_id": "T1",
            "event": {
                "type": "message",
                "channel": "C1",
                "thread_ts": "170.0001",
                "text": "export",
                "bot_id": "B1",
            },
        },
        ack=lambda: None,
        client=client,
    )

    assert [call for call in client.calls if call[0] == "chat_postMessage"] == [
        (
            "chat_postMessage",
            {
                "channel": "C1",
                "thread_ts": "170.0001",
                "text": "Explanation request noted. This task slice only records the thread state; no Claude analysis runs yet.",
            },
        )
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.EXPLANATION_REQUESTED


def test_message_invalid_transitions_reply_without_mutating_terminal_state() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPORT)
    store.apply_command(key, CanonicalCommand.CONFIRM)

    handler.handle_message(
        body={
            "event_id": "Ev2",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "explain"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev3",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )

    assert [payload[1]["text"] for payload in client.calls if payload[0] == "chat_postMessage"] == [
        "This thread has already finished its export decision. Please share a new MP4 in a new thread to start over.",
        "This thread has already finished its export decision. Please share a new MP4 in a new thread to start over.",
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CONFIRMATION_CONSUMED


def test_register_slack_handlers_wires_file_and_message_events() -> None:
    handler, _ = make_handler()
    app = FakeApp()

    register_slack_handlers(app, handler)

    assert sorted(app.handlers) == ["file_shared", "message"]
