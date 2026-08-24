from __future__ import annotations

import logging
from typing import Any

from slack_video_assistant.explanation_orchestrator import ExplanationOrchestrator
from slack_video_assistant.session_store import (
    CanonicalCommand,
    ExportRequest,
    SessionKey,
    SessionStatus,
    ThreadSessionStore,
)
from slack_video_assistant.slack_events import (
    EXPORT_RATIO_ACTION_ID,
    ProcessedEventStore,
    SlackEventHandler,
    register_slack_handlers,
)
from slack_video_assistant.slack_file_adapter import SlackFileAdapter


class FakeSlackClient:
    def __init__(self, file_response: dict[str, Any]) -> None:
        self.file_response = file_response
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._message_counter = 0

    def files_info(self, *, file: str) -> dict[str, Any]:
        self.calls.append(("files_info", {"file": file}))
        return self.file_response

    def chat_postMessage(self, **payload: Any) -> None:
        self.calls.append(("chat_postMessage", payload))
        self._message_counter += 1
        return {"ts": f"171.000{self._message_counter}"}

    def chat_update(self, **payload: Any) -> None:
        self.calls.append(("chat_update", payload))
        return {"ts": payload["ts"]}


class FailOnceUpdatingSlackClient(FakeSlackClient):
    def __init__(self, file_response: dict[str, Any]) -> None:
        super().__init__(file_response)
        self._failed = False

    def chat_update(self, **payload: Any) -> None:
        self.calls.append(("chat_update", payload))
        if not self._failed:
            self._failed = True
            raise RuntimeError("message_not_found")
        return {"ts": payload["ts"]}


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




class RecordingExplanationOrchestrator:
    def __init__(self) -> None:
        self.sessions = []
        self.cancel_status = "accepted"
        self.cancel_calls = []

    def enqueue(self, *, client: Any, session) -> None:
        self.sessions.append((client, session))

    def request_cancel(self, key: SessionKey) -> str:
        self.cancel_calls.append(key)
        return self.cancel_status


class RaisingExplanationOrchestrator:
    def __init__(self) -> None:
        self.calls = 0

    def enqueue(self, *, client: Any, session) -> None:
        self.calls += 1
        raise RuntimeError("executor failed")


class RecordingExportExecutor:
    def __init__(self) -> None:
        self.requests: list[tuple[Any, ExportRequest]] = []

    def submit(self, *, client: Any, request: ExportRequest) -> None:
        self.requests.append((client, request))

class FakeApp:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def event(self, name: str):
        def _register(handler):
            self.handlers[name] = handler
            return handler

        return _register

    def action(self, name: str):
        def _register(handler):
            self.handlers[f"action:{name}"] = handler
            return handler

        return _register


def make_handler(
    explanation_orchestrator: ExplanationOrchestrator | RecordingExplanationOrchestrator | None = None,
    export_executor: RecordingExportExecutor | None = None,
) -> tuple[SlackEventHandler, ThreadSessionStore]:
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
            explanation_orchestrator=explanation_orchestrator,
            export_executor=export_executor,
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
    export_executor = RecordingExportExecutor()
    handler, store = make_handler(export_executor=export_executor)
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
    assert export_executor.requests == []
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
        "I suggest a 16:9 MP4 export with a centered crop for this MVP. Choose one of the approved ratios below, then reply with `confirm` to continue or `cancel` to stop.",
        "A 16:9 export suggestion with a centered crop is already pending for this thread. Reply with `confirm` or `cancel`.",
        "Confirmation recorded. I handed the approved 16:9 centered-crop export request to the next execution step.",
        "There is no pending export to confirm in this thread.",
    ]
    export_payload = [payload for name, payload in client.calls if name == "chat_postMessage"][0]
    assert export_payload["blocks"][0]["accessory"]["action_id"] == EXPORT_RATIO_ACTION_ID
    assert [option["value"] for option in export_payload["blocks"][0]["accessory"]["options"]] == [
        "16:9",
        "9:16",
        "1:1",
        "4:3",
        "3:4",
    ]
    assert export_executor.requests == [
        (
            client,
            ExportRequest(key=key, file_id="F1", target_ratio="16:9"),
        )
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CONFIRMATION_CONSUMED


def test_confirm_without_export_executor_reports_saved_confirmation_without_handoff_claim() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPORT)

    handler.handle_message(
        body={
            "event_id": "Ev-confirm-no-executor",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "confirm"},
        },
        ack=lambda: None,
        client=client,
    )

    assert [payload[1]["text"] for payload in client.calls if payload[0] == "chat_postMessage"] == [
        "Confirmation recorded. The approved 16:9 centered-crop export request is saved for this thread.",
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CONFIRMATION_CONSUMED


def test_export_requires_eligible_video_session_and_does_not_submit_executor() -> None:
    export_executor = RecordingExportExecutor()
    handler, _ = make_handler(export_executor=export_executor)
    client = FakeSlackClient(make_file_response())

    handler.handle_message(
        body={
            "event_id": "Ev-export-missing",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )

    assert export_executor.requests == []
    assert [payload[1]["text"] for payload in client.calls if payload[0] == "chat_postMessage"] == [
        "Please share an MP4 in this thread first so I can track the request.",
    ]


def test_cancel_pending_export_clears_state_without_executor_side_effects() -> None:
    export_executor = RecordingExportExecutor()
    handler, store = make_handler(export_executor=export_executor)
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPORT)

    handler.handle_message(
        body={
            "event_id": "Ev-cancel-export-1",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "cancel"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev-cancel-export-2",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "cancel"},
        },
        ack=lambda: None,
        client=client,
    )

    assert export_executor.requests == []
    assert [payload[1]["text"] for payload in client.calls if payload[0] == "chat_postMessage"] == [
        "Export request cancelled for this thread.",
        "There is no active explanation or pending export to cancel in this thread.",
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CANCELLATION_CONSUMED


def test_confirm_is_thread_isolated_and_does_not_submit_other_thread_request() -> None:
    export_executor = RecordingExportExecutor()
    handler, store = make_handler(export_executor=export_executor)
    client = FakeSlackClient(make_file_response())
    first_key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    second_key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0002")
    store.receive_video(first_key, file_id="F1")
    store.receive_video(second_key, file_id="F2")
    store.apply_command(first_key, CanonicalCommand.EXPORT)

    handler.handle_message(
        body={
            "event_id": "Ev-confirm-wrong-thread",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0002", "text": "confirm"},
        },
        ack=lambda: None,
        client=client,
    )

    assert export_executor.requests == []
    assert [payload[1]["text"] for payload in client.calls if payload[0] == "chat_postMessage"] == [
        "There is no pending export to confirm in this thread.",
    ]
    first_session = store.get(first_key)
    second_session = store.get(second_key)
    assert first_session is not None
    assert first_session.status is SessionStatus.EXPORT_PENDING
    assert second_session is not None
    assert second_session.status is SessionStatus.VIDEO_RECEIVED


def test_ratio_action_acknowledges_updates_pending_selection_and_does_not_start_export() -> None:
    export_executor = RecordingExportExecutor()
    handler, store = make_handler(export_executor=export_executor)
    client = FakeSlackClient(make_file_response())
    order: list[str] = []
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev-export-action-1",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )

    handler.handle_export_ratio_action(
        body={
            "team": {"id": "T1"},
            "channel": {"id": "C1"},
            "container": {"channel_id": "C1", "message_ts": "171.0001"},
            "message": {"thread_ts": "170.0001", "ts": "171.0001"},
            "actions": [
                {
                    "action_id": EXPORT_RATIO_ACTION_ID,
                    "action_ts": "172.0001",
                    "selected_option": {"value": "4:3"},
                }
            ],
        },
        ack=lambda: order.append("ack"),
        client=client,
    )

    assert order == ["ack"]
    assert export_executor.requests == []
    update_payloads = [payload for name, payload in client.calls if name == "chat_update"]
    assert len(update_payloads) == 1
    assert update_payloads[0]["ts"] == "171.0001"
    assert update_payloads[0]["blocks"][0]["accessory"]["initial_option"]["value"] == "4:3"
    session = store.get(key)
    assert session is not None
    assert session.pending_export is not None
    assert session.pending_export.target_ratio == "4:3"


def test_ratio_action_confirm_uses_latest_selected_ratio() -> None:
    export_executor = RecordingExportExecutor()
    handler, store = make_handler(export_executor=export_executor)
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev-export-action-2",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_export_ratio_action(
        body={
            "team": {"id": "T1"},
            "channel": {"id": "C1"},
            "container": {"channel_id": "C1", "message_ts": "171.0001"},
            "message": {"thread_ts": "170.0001", "ts": "171.0001"},
            "actions": [
                {
                    "action_id": EXPORT_RATIO_ACTION_ID,
                    "action_ts": "172.0002",
                    "selected_option": {"value": "3:4"},
                }
            ],
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev-confirm-action-2",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "confirm"},
        },
        ack=lambda: None,
        client=client,
    )

    assert export_executor.requests == [
        (
            client,
            ExportRequest(key=key, file_id="F1", target_ratio="3:4"),
        )
    ]


def test_ratio_action_rejects_missing_message_ts_when_pending_export_message_is_bound() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev-export-action-missing-ts",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )

    handler.handle_export_ratio_action(
        body={
            "team": {"id": "T1"},
            "channel": {"id": "C1"},
            "container": {"channel_id": "C1"},
            "message": {"thread_ts": "170.0001", "ts": "171.0001"},
            "actions": [
                {
                    "action_id": EXPORT_RATIO_ACTION_ID,
                    "action_ts": "172.1001",
                    "selected_option": {"value": "4:3"},
                }
            ],
        },
        ack=lambda: None,
        client=client,
    )

    assert [payload for name, payload in client.calls if name == "chat_update"] == []
    session = store.get(key)
    assert session is not None
    assert session.pending_export is not None
    assert session.pending_export.target_ratio == "16:9"
    assert session.pending_export.message_ts == "171.0001"


def test_ratio_action_rebinds_pending_export_after_update_fallback_so_next_action_stays_usable() -> None:
    handler, store = make_handler()
    client = FailOnceUpdatingSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev-export-action-rebind",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )

    first_action = {
        "team": {"id": "T1"},
        "channel": {"id": "C1"},
        "container": {"channel_id": "C1", "message_ts": "171.0001"},
        "message": {"thread_ts": "170.0001", "ts": "171.0001"},
        "actions": [
            {
                "action_id": EXPORT_RATIO_ACTION_ID,
                "action_ts": "172.2001",
                "selected_option": {"value": "4:3"},
            }
        ],
    }
    handler.handle_export_ratio_action(body=first_action, ack=lambda: None, client=client)

    rebound_session = store.get(key)
    assert rebound_session is not None
    assert rebound_session.pending_export is not None
    assert rebound_session.pending_export.target_ratio == "4:3"
    assert rebound_session.pending_export.message_ts == "171.0002"

    second_action = {
        "team": {"id": "T1"},
        "channel": {"id": "C1"},
        "container": {"channel_id": "C1", "message_ts": "171.0002"},
        "message": {"thread_ts": "170.0001", "ts": "171.0002"},
        "actions": [
            {
                "action_id": EXPORT_RATIO_ACTION_ID,
                "action_ts": "172.2002",
                "selected_option": {"value": "3:4"},
            }
        ],
    }
    handler.handle_export_ratio_action(body=second_action, ack=lambda: None, client=client)

    update_payloads = [payload for name, payload in client.calls if name == "chat_update"]
    post_payloads = [payload for name, payload in client.calls if name == "chat_postMessage"]
    assert [payload["ts"] for payload in update_payloads] == ["171.0001", "171.0002"]
    assert len(post_payloads) == 2
    final_session = store.get(key)
    assert final_session is not None
    assert final_session.pending_export is not None
    assert final_session.pending_export.target_ratio == "3:4"
    assert final_session.pending_export.message_ts == "171.0002"


def test_ratio_action_duplicate_and_invalid_payloads_are_safe_and_idempotent() -> None:
    export_executor = RecordingExportExecutor()
    handler, store = make_handler(export_executor=export_executor)
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev-export-action-3",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "export"},
        },
        ack=lambda: None,
        client=client,
    )

    duplicate_body = {
        "team": {"id": "T1"},
        "channel": {"id": "C1"},
        "container": {"channel_id": "C1", "message_ts": "171.0001"},
        "message": {"thread_ts": "170.0001", "ts": "171.0001"},
        "actions": [
            {
                "action_id": EXPORT_RATIO_ACTION_ID,
                "action_ts": "172.0003",
                "selected_option": {"value": "4:3"},
            }
        ],
    }
    handler.handle_export_ratio_action(body=duplicate_body, ack=lambda: None, client=client)
    handler.handle_export_ratio_action(body=duplicate_body, ack=lambda: None, client=client)
    handler.handle_export_ratio_action(
        body={
            "team": {"id": "T1"},
            "channel": {"id": "C1"},
            "container": {"channel_id": "C1", "message_ts": "171.9999"},
            "message": {"thread_ts": "170.0001", "ts": "171.9999"},
            "actions": [
                {
                    "action_id": EXPORT_RATIO_ACTION_ID,
                    "action_ts": "172.0004",
                    "selected_option": {"value": "21:9"},
                }
            ],
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev-cancel-action-3",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "cancel"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_export_ratio_action(
        body={
            "team": {"id": "T1"},
            "channel": {"id": "C1"},
            "container": {"channel_id": "C1", "message_ts": "171.0001"},
            "message": {"thread_ts": "170.0001", "ts": "171.0001"},
            "actions": [
                {
                    "action_id": EXPORT_RATIO_ACTION_ID,
                    "action_ts": "172.0005",
                    "selected_option": {"value": "3:4"},
                }
            ],
        },
        ack=lambda: None,
        client=client,
    )

    assert export_executor.requests == []
    assert len([payload for name, payload in client.calls if name == "chat_update"]) == 1
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CANCELLATION_CONSUMED


def test_cancel_active_explanation_requests_cooperative_cancellation() -> None:
    orchestrator = RecordingExplanationOrchestrator()
    handler, store = make_handler(orchestrator)
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPLAIN)

    handler.handle_message(
        body={
            "event_id": "Ev-cancel-active",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "cancel"},
        },
        ack=lambda: None,
        client=client,
    )

    assert orchestrator.cancel_calls == [key]
    assert [call for call in client.calls if call[0] == "chat_postMessage"] == [
        (
            "chat_postMessage",
            {
                "channel": "C1",
                "thread_ts": "170.0001",
                "text": "Okay — I’ll stop this explanation and clean up the temporary workspace.",
            },
        )
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.EXPLANATION_CANCELLED


def test_cancel_completed_or_missing_explanation_returns_safe_noop() -> None:
    orchestrator = RecordingExplanationOrchestrator()
    handler, store = make_handler(orchestrator)
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPLAIN)
    orchestrator.cancel_status = "publication_started"

    handler.handle_message(
        body={
            "event_id": "Ev-cancel-finished",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "cancel"},
        },
        ack=lambda: None,
        client=client,
    )
    handler.handle_message(
        body={
            "event_id": "Ev-cancel-missing",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.9999", "text": "cancel"},
        },
        ack=lambda: None,
        client=client,
    )

    assert [payload[1]["text"] for payload in client.calls if payload[0] == "chat_postMessage"] == [
        "The explanation has already finished, so there is nothing to cancel.",
        "Please share an MP4 in this thread first so I can track the request.",
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.EXPLANATION_REQUESTED


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




def test_missing_explanation_orchestrator_posts_safe_failure_without_mutating_session() -> None:
    handler, store = make_handler()
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id='T1', channel_id='C1', thread_ts='170.0001')
    store.receive_video(key, file_id='F1')

    handler.handle_message(
        body={
            'event_id': 'Ev-missing-orchestrator',
            'team_id': 'T1',
            'event': {'type': 'message', 'channel': 'C1', 'thread_ts': '170.0001', 'text': 'explain'},
        },
        ack=lambda: None,
        client=client,
    )

    assert [call for call in client.calls if call[0] == 'chat_postMessage'] == [
        (
            'chat_postMessage',
            {
                'channel': 'C1',
                'thread_ts': '170.0001',
                'text': "I couldn't start the explanation job safely. Please try again in this thread.",
            },
        )
    ]
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.VIDEO_RECEIVED




def test_explain_enqueue_failure_posts_safe_error_and_allows_retry() -> None:
    failing_orchestrator = RaisingExplanationOrchestrator()
    handler, store = make_handler(failing_orchestrator)
    client = FakeSlackClient(make_file_response())
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.0001")
    store.receive_video(key, file_id="F1")

    handler.handle_message(
        body={
            "event_id": "Ev-raise-1",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "explain"},
        },
        ack=lambda: None,
        client=client,
    )

    session = store.get(key)
    assert failing_orchestrator.calls == 1
    assert session is not None
    assert session.status is SessionStatus.VIDEO_RECEIVED
    assert [call for call in client.calls if call[0] == "chat_postMessage"] == [
        (
            "chat_postMessage",
            {
                "channel": "C1",
                "thread_ts": "170.0001",
                "text": "I couldn't start the explanation job safely. Please try again in this thread.",
            },
        )
    ]

    retry_orchestrator = RecordingExplanationOrchestrator()
    retry_handler = SlackEventHandler(
        file_adapter_factory=handler._file_adapter_factory,
        session_store=store,
        processed_events=ProcessedEventStore(),
        logger=logging.getLogger("tests.slack_events.retry"),
        explanation_orchestrator=retry_orchestrator,
    )
    retry_client = FakeSlackClient(make_file_response())

    retry_handler.handle_message(
        body={
            "event_id": "Ev-raise-2",
            "team_id": "T1",
            "event": {"type": "message", "channel": "C1", "thread_ts": "170.0001", "text": "explain"},
        },
        ack=lambda: None,
        client=retry_client,
    )

    session = store.get(key)
    assert len(retry_orchestrator.sessions) == 1
    assert session is not None
    assert session.status is SessionStatus.EXPLANATION_REQUESTED
    assert [call for call in retry_client.calls if call[0] == "chat_postMessage"] == [
        (
            "chat_postMessage",
            {
                "channel": "C1",
                "thread_ts": "170.0001",
                "text": "I’m preparing an explanation for this video now. I’ll reply in this thread when it’s ready.",
            },
        )
    ]


def test_retried_event_and_bot_message_do_not_duplicate_effects() -> None:
    orchestrator = RecordingExplanationOrchestrator()
    handler, store = make_handler(orchestrator)
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
                "text": "I’m preparing an explanation for this video now. I’ll reply in this thread when it’s ready.",
            },
        )
    ]
    assert len(orchestrator.sessions) == 1
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

    assert sorted(app.handlers) == ["action:export_ratio_select", "file_shared", "message"]
