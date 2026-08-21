from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import Any, Callable, Mapping

from slack_video_assistant.explanation_orchestrator import ExplanationOrchestrator
from slack_video_assistant.logging_utils import redact_sensitive
from slack_video_assistant.session_store import (
    CanonicalCommand,
    SessionKey,
    ThreadSessionStore,
    TransitionResult,
)
from slack_video_assistant.slack_file_adapter import SlackAdapterError, SlackFileAdapter, is_supported_mp4


AckCallable = Callable[[], None]


@dataclass(frozen=True)
class ThreadContext:
    team_id: str
    channel_id: str
    thread_ts: str | None


class ProcessedEventStore:
    def __init__(self) -> None:
        self._event_ids: set[str] = set()

    def mark_processed(self, event_id: str | None) -> bool:
        if not event_id:
            return True
        if event_id in self._event_ids:
            return False
        self._event_ids.add(event_id)
        return True


class SlackEventHandler:
    def __init__(
        self,
        *,
        file_adapter_factory: Callable[[Any], SlackFileAdapter],
        session_store: ThreadSessionStore,
        processed_events: ProcessedEventStore,
        logger: Logger,
        explanation_orchestrator: ExplanationOrchestrator | None = None,
    ) -> None:
        self._file_adapter_factory = file_adapter_factory
        self._session_store = session_store
        self._processed_events = processed_events
        self._logger = logger
        self._explanation_orchestrator = explanation_orchestrator

    def handle_file_shared(self, *, body: Mapping[str, Any], ack: AckCallable, client: Any) -> None:
        ack()
        if not self._processed_events.mark_processed(_event_id(body)):
            return

        event = _event(body)
        file_id = str(event.get("file_id", "")).strip()
        if not file_id:
            return

        adapter = self._file_adapter_factory(client)
        context = _fallback_thread_context(body)
        try:
            file_record = adapter.get_file_record(file_id)
            context = _resolve_thread_context(body, file_record.raw)
        except SlackAdapterError as exc:
            self._logger.error("Slack file handling failed: %s", redact_sensitive(exc))
            self._notify_file_share_failure(client=client, context=context)
            return

        if not context.channel_id:
            return

        if not context.thread_ts:
            self._post_message(
                client,
                channel=context.channel_id,
                text="Please share the MP4 from inside a Slack thread so I can keep the workflow in one place.",
            )
            return

        if not is_supported_mp4(file_record):
            self._post_message(
                client,
                channel=context.channel_id,
                thread_ts=context.thread_ts,
                text="I can only work with MP4 uploads for this MVP. Please share an MP4 in this thread.",
            )
            return

        key = SessionKey(
            team_id=context.team_id,
            channel_id=context.channel_id,
            thread_ts=context.thread_ts,
        )
        transition = self._session_store.receive_video(key, file_id=file_record.file_id)
        if not transition.state_changed:
            return

        self._post_message(
            client,
            channel=context.channel_id,
            thread_ts=context.thread_ts,
            text=(
                "I found your MP4. Reply with `explain` for a summary or `export` to start the export confirmation flow."
            ),
        )

    def handle_message(self, *, body: Mapping[str, Any], ack: AckCallable, client: Any) -> None:
        ack()
        if not self._processed_events.mark_processed(_event_id(body)):
            return

        event = _event(body)
        if _is_bot_message(event):
            return

        command = _canonical_command(str(event.get("text", "")))
        if command is None:
            return

        context = ThreadContext(
            team_id=_team_id(body),
            channel_id=str(event.get("channel", "")).strip(),
            thread_ts=str(event.get("thread_ts", "")).strip() or None,
        )
        if not context.team_id or not context.channel_id or not context.thread_ts:
            return

        key = SessionKey(
            team_id=context.team_id,
            channel_id=context.channel_id,
            thread_ts=context.thread_ts,
        )
        result = self._session_store.apply_command(key, command)
        if command is CanonicalCommand.EXPLAIN and result.reason == "explanation_requested" and result.session:
            self._post_message(
                client,
                channel=context.channel_id,
                thread_ts=context.thread_ts,
                text="I’m preparing an explanation for this video now. I’ll reply in this thread when it’s ready.",
            )
            if self._explanation_orchestrator is not None:
                try:
                    self._explanation_orchestrator.enqueue(client=client, session=result.session)
                except Exception:
                    self._logger.exception("Explanation orchestration failed to start")
                    self._post_message(
                        client,
                        channel=context.channel_id,
                        thread_ts=context.thread_ts,
                        text="I couldn't start the explanation job safely. Please try again in this thread.",
                    )
            return

        self._post_message(
            client,
            channel=context.channel_id,
            thread_ts=context.thread_ts,
            text=_message_for_transition(command, result),
        )

    def _post_message(
        self,
        client: Any,
        *,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        try:
            client.chat_postMessage(**payload)
        except Exception as exc:
            self._logger.error("Slack message publish failed: %s", redact_sensitive(exc))

    def _notify_file_share_failure(self, *, client: Any, context: ThreadContext) -> None:
        if not context.channel_id:
            return

        message = "I couldn't read this Slack upload safely. Please share the MP4 in this thread again."
        if not context.thread_ts:
            message = "I couldn't read this Slack upload safely. Please share the MP4 from inside a Slack thread and try again."

        self._post_message(
            client,
            channel=context.channel_id,
            thread_ts=context.thread_ts,
            text=message,
        )


def register_slack_handlers(app: Any, handler: SlackEventHandler) -> None:
    @app.event("file_shared")
    def _on_file_shared(body: Mapping[str, Any], ack: AckCallable, client: Any) -> None:
        handler.handle_file_shared(body=body, ack=ack, client=client)

    @app.event("message")
    def _on_message(body: Mapping[str, Any], ack: AckCallable, client: Any) -> None:
        handler.handle_message(body=body, ack=ack, client=client)


def _event(body: Mapping[str, Any]) -> Mapping[str, Any]:
    return body.get("event", {}) if isinstance(body.get("event"), Mapping) else {}


def _event_id(body: Mapping[str, Any]) -> str | None:
    event_id = body.get("event_id")
    if event_id:
        return str(event_id)
    event = _event(body)
    event_type = str(event.get("type", ""))
    if event_type == "file_shared":
        return f"file_shared:{event.get('file_id', '')}:{event.get('event_ts', '')}"
    return f"message:{event.get('channel', '')}:{event.get('ts', '')}:{str(event.get('text', '')).strip().lower()}"


def _team_id(body: Mapping[str, Any]) -> str:
    team_id = str(body.get("team_id", "")).strip()
    if team_id:
        return team_id
    authorizations = body.get("authorizations", [])
    if isinstance(authorizations, list):
        for authorization in authorizations:
            if isinstance(authorization, Mapping):
                candidate = str(authorization.get("team_id", "")).strip()
                if candidate:
                    return candidate
    return ""


def _resolve_thread_context(body: Mapping[str, Any], file_info: Mapping[str, Any]) -> ThreadContext:
    event = _event(body)
    explicit_channel = str(event.get("channel_id", "") or event.get("channel", "")).strip()
    explicit_thread = str(event.get("thread_ts", "")).strip() or None
    team_id = _team_id(body)
    if explicit_channel and explicit_thread:
        return ThreadContext(team_id=team_id, channel_id=explicit_channel, thread_ts=explicit_thread)

    shares = file_info.get("shares", {}) if isinstance(file_info.get("shares"), Mapping) else {}
    return _extract_thread_context_from_shares(team_id=team_id, shares=shares, preferred_channel=explicit_channel)


def _extract_thread_context_from_shares(
    *,
    team_id: str,
    shares: Mapping[str, Any],
    preferred_channel: str,
) -> ThreadContext:
    candidates = _share_candidates(shares)
    if preferred_channel:
        matching = [candidate for candidate in candidates if candidate[0] == preferred_channel]
        if len(matching) == 1:
            channel_id, thread_ts = matching[0]
            return ThreadContext(team_id=team_id, channel_id=channel_id, thread_ts=thread_ts)
        return ThreadContext(team_id=team_id, channel_id=preferred_channel, thread_ts=None)

    if len(candidates) == 1:
        channel_id, thread_ts = candidates[0]
        return ThreadContext(team_id=team_id, channel_id=channel_id, thread_ts=thread_ts)

    unique_channels = {channel_id for channel_id, _ in candidates}
    if len(unique_channels) == 1:
        return ThreadContext(team_id=team_id, channel_id=next(iter(unique_channels)), thread_ts=None)

    return ThreadContext(team_id=team_id, channel_id="", thread_ts=None)


def _share_candidates(shares: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    channel_maps: list[Mapping[str, Any]] = []
    for share_type in ("public", "private"):
        share_map = shares.get(share_type)
        if isinstance(share_map, Mapping):
            channel_maps.append(share_map)

    seen: set[tuple[str, str | None]] = set()
    candidates: list[tuple[str, str | None]] = []
    for channel_map in channel_maps:
        for channel_id, entries in channel_map.items():
            if not isinstance(entries, list) or not entries:
                continue
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                normalized_channel = str(channel_id).strip()
                if not normalized_channel:
                    continue
                thread_ts = str(entry.get("thread_ts", "")).strip() or None
                candidate = (normalized_channel, thread_ts)
                if candidate in seen:
                    continue
                seen.add(candidate)
                candidates.append(candidate)
    return candidates


def _fallback_thread_context(body: Mapping[str, Any]) -> ThreadContext:
    event = _event(body)
    return ThreadContext(
        team_id=_team_id(body),
        channel_id=str(event.get("channel_id", "") or event.get("channel", "")).strip(),
        thread_ts=str(event.get("thread_ts", "")).strip() or None,
    )


def _is_bot_message(event: Mapping[str, Any]) -> bool:
    return bool(event.get("bot_id")) or str(event.get("subtype", "")) == "bot_message"


def _canonical_command(text: str) -> CanonicalCommand | None:
    normalized = text.strip().lower()
    try:
        return CanonicalCommand(normalized)
    except ValueError:
        return None


def _message_for_transition(command: CanonicalCommand, result: TransitionResult) -> str:
    if result.reason == "missing_session":
        return "Please share an MP4 in this thread first so I can track the request."

    if command is CanonicalCommand.EXPLAIN:
        if result.reason == "explanation_requested":
            return "I’m preparing an explanation for this video now. I’ll reply in this thread when it’s ready."
        if result.reason == "export_confirmation_pending":
            return "An export confirmation is already pending for this thread. Reply with `confirm` or `cancel` before requesting anything else."
        if result.reason == "explanation_no_longer_available":
            return "This thread has already finished its export decision. Please share a new MP4 in a new thread to start over."
        return "Explanation has already been requested for this thread."

    if command is CanonicalCommand.EXPORT:
        if result.reason == "export_pending":
            return "Export request noted. Reply with `confirm` to continue or `cancel` to stop."
        if result.reason == "export_no_longer_available":
            return "This thread has already finished its export decision. Please share a new MP4 in a new thread to start over."
        return "An export confirmation is already pending for this thread."

    if command is CanonicalCommand.CONFIRM:
        if result.reason == "confirmation_consumed":
            return "Confirmation recorded. This task slice stops before FFmpeg export work starts."
        return "There is no pending export to confirm in this thread."

    if result.reason == "cancellation_consumed":
        return "Export request cancelled for this thread."
    return "There is no pending export to cancel in this thread."
