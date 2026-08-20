from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionStatus(str, Enum):
    VIDEO_RECEIVED = "video_received"
    EXPLANATION_REQUESTED = "explanation_requested"
    EXPORT_PENDING = "export_pending"
    CONFIRMATION_CONSUMED = "confirmation_consumed"
    CANCELLATION_CONSUMED = "cancellation_consumed"


class CanonicalCommand(str, Enum):
    EXPLAIN = "explain"
    EXPORT = "export"
    CONFIRM = "confirm"
    CANCEL = "cancel"


@dataclass(frozen=True)
class SessionKey:
    team_id: str
    channel_id: str
    thread_ts: str


@dataclass(frozen=True)
class ThreadSession:
    key: SessionKey
    file_id: str
    status: SessionStatus


@dataclass(frozen=True)
class TransitionResult:
    state_changed: bool
    session: ThreadSession | None
    reason: str


class ThreadSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[SessionKey, ThreadSession] = {}

    def get(self, key: SessionKey) -> ThreadSession | None:
        return self._sessions.get(key)

    def receive_video(self, key: SessionKey, *, file_id: str) -> TransitionResult:
        next_session = ThreadSession(key=key, file_id=file_id, status=SessionStatus.VIDEO_RECEIVED)
        previous = self._sessions.get(key)
        state_changed = previous != next_session
        self._sessions[key] = next_session
        return TransitionResult(
            state_changed=state_changed,
            session=next_session,
            reason="video_recorded" if state_changed else "duplicate_video",
        )

    def apply_command(self, key: SessionKey, command: CanonicalCommand) -> TransitionResult:
        session = self._sessions.get(key)
        if session is None:
            return TransitionResult(state_changed=False, session=None, reason="missing_session")

        if command is CanonicalCommand.EXPLAIN:
            return self._transition(
                key,
                session,
                target=SessionStatus.EXPLANATION_REQUESTED,
                duplicate_reason="explanation_already_requested",
                success_reason="explanation_requested",
            )

        if command is CanonicalCommand.EXPORT:
            return self._transition(
                key,
                session,
                target=SessionStatus.EXPORT_PENDING,
                duplicate_reason="export_already_pending",
                success_reason="export_pending",
            )

        if command is CanonicalCommand.CONFIRM:
            if session.status is not SessionStatus.EXPORT_PENDING:
                return TransitionResult(state_changed=False, session=session, reason="missing_pending_export")
            return self._replace(key, session, SessionStatus.CONFIRMATION_CONSUMED, "confirmation_consumed")

        if session.status is not SessionStatus.EXPORT_PENDING:
            return TransitionResult(state_changed=False, session=session, reason="nothing_to_cancel")
        return self._replace(key, session, SessionStatus.CANCELLATION_CONSUMED, "cancellation_consumed")

    def _transition(
        self,
        key: SessionKey,
        session: ThreadSession,
        *,
        target: SessionStatus,
        duplicate_reason: str,
        success_reason: str,
    ) -> TransitionResult:
        if session.status is target:
            return TransitionResult(state_changed=False, session=session, reason=duplicate_reason)
        return self._replace(key, session, target, success_reason)

    def _replace(
        self,
        key: SessionKey,
        session: ThreadSession,
        target: SessionStatus,
        reason: str,
    ) -> TransitionResult:
        next_session = ThreadSession(key=key, file_id=session.file_id, status=target)
        self._sessions[key] = next_session
        return TransitionResult(state_changed=True, session=next_session, reason=reason)
