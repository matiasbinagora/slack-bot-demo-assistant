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
            if session.status is SessionStatus.VIDEO_RECEIVED:
                return self._replace(key, session, SessionStatus.EXPLANATION_REQUESTED, "explanation_requested")
            if session.status is SessionStatus.EXPLANATION_REQUESTED:
                return TransitionResult(state_changed=False, session=session, reason="explanation_already_requested")
            if session.status is SessionStatus.EXPORT_PENDING:
                return TransitionResult(state_changed=False, session=session, reason="export_confirmation_pending")
            return TransitionResult(state_changed=False, session=session, reason="explanation_no_longer_available")

        if command is CanonicalCommand.EXPORT:
            if session.status in (SessionStatus.VIDEO_RECEIVED, SessionStatus.EXPLANATION_REQUESTED):
                return self._replace(key, session, SessionStatus.EXPORT_PENDING, "export_pending")
            if session.status is SessionStatus.EXPORT_PENDING:
                return TransitionResult(state_changed=False, session=session, reason="export_already_pending")
            return TransitionResult(state_changed=False, session=session, reason="export_no_longer_available")

        if command is CanonicalCommand.CONFIRM:
            if session.status is not SessionStatus.EXPORT_PENDING:
                return TransitionResult(state_changed=False, session=session, reason="missing_pending_export")
            return self._replace(key, session, SessionStatus.CONFIRMATION_CONSUMED, "confirmation_consumed")

        if session.status is not SessionStatus.EXPORT_PENDING:
            return TransitionResult(state_changed=False, session=session, reason="nothing_to_cancel")
        return self._replace(key, session, SessionStatus.CANCELLATION_CONSUMED, "cancellation_consumed")

    def rollback_explain_request(self, key: SessionKey) -> TransitionResult:
        session = self._sessions.get(key)
        if session is None:
            return TransitionResult(state_changed=False, session=None, reason="missing_session")
        if session.status is not SessionStatus.EXPLANATION_REQUESTED:
            return TransitionResult(state_changed=False, session=session, reason="rollback_not_needed")
        return self._replace(key, session, SessionStatus.VIDEO_RECEIVED, "explanation_rollback")

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
