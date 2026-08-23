from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


DEFAULT_EXPORT_RATIO = "16:9"
SUPPORTED_EXPORT_RATIOS = ("16:9", "9:16", "1:1")


class SessionStatus(str, Enum):
    VIDEO_RECEIVED = "video_received"
    EXPLANATION_REQUESTED = "explanation_requested"
    EXPLANATION_CANCELLED = "explanation_cancelled"
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
class ExportSuggestion:
    target_ratio: str
    crop_mode: str = "centered"


@dataclass(frozen=True)
class ExportRequest:
    key: SessionKey
    file_id: str
    target_ratio: str


class ExportExecutor(Protocol):
    def submit(self, *, client: Any, request: ExportRequest) -> None: ...


@dataclass(frozen=True)
class ThreadSession:
    key: SessionKey
    file_id: str
    status: SessionStatus
    pending_export: ExportSuggestion | None = None


@dataclass(frozen=True)
class TransitionResult:
    state_changed: bool
    session: ThreadSession | None
    reason: str
    export_request: ExportRequest | None = None


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

    def apply_command(
        self,
        key: SessionKey,
        command: CanonicalCommand,
        *,
        explanation_cancel_status: str | None = None,
    ) -> TransitionResult:
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
                return self._replace(
                    key,
                    session,
                    SessionStatus.EXPORT_PENDING,
                    "export_pending",
                    pending_export=self._build_export_suggestion(session),
                )
            if session.status is SessionStatus.EXPORT_PENDING:
                return TransitionResult(state_changed=False, session=session, reason="export_already_pending")
            return TransitionResult(state_changed=False, session=session, reason="export_no_longer_available")

        if command is CanonicalCommand.CONFIRM:
            if session.status is not SessionStatus.EXPORT_PENDING or session.pending_export is None:
                return TransitionResult(state_changed=False, session=session, reason="missing_pending_export")
            export_request = ExportRequest(
                key=key,
                file_id=session.file_id,
                target_ratio=session.pending_export.target_ratio,
            )
            return self._replace(
                key,
                session,
                SessionStatus.CONFIRMATION_CONSUMED,
                "confirmation_consumed",
                export_request=export_request,
            )

        if session.status is SessionStatus.EXPORT_PENDING:
            return self._replace(key, session, SessionStatus.CANCELLATION_CONSUMED, "cancellation_consumed")
        if session.status is SessionStatus.EXPLANATION_CANCELLED:
            return TransitionResult(state_changed=False, session=session, reason="explanation_already_cancelled")
        if session.status is SessionStatus.EXPLANATION_REQUESTED:
            if explanation_cancel_status in {"accepted", "already_requested"}:
                return self._replace(key, session, SessionStatus.EXPLANATION_CANCELLED, "explanation_cancelled")
            if explanation_cancel_status in {"publication_started", "terminal"}:
                return TransitionResult(state_changed=False, session=session, reason="explanation_already_completed")
        return TransitionResult(state_changed=False, session=session, reason="nothing_to_cancel")

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
        *,
        pending_export: ExportSuggestion | None = None,
        export_request: ExportRequest | None = None,
    ) -> TransitionResult:
        next_pending_export = pending_export if target is SessionStatus.EXPORT_PENDING else None
        next_session = ThreadSession(
            key=key,
            file_id=session.file_id,
            status=target,
            pending_export=next_pending_export,
        )
        self._sessions[key] = next_session
        return TransitionResult(
            state_changed=True,
            session=next_session,
            reason=reason,
            export_request=export_request,
        )

    def _build_export_suggestion(self, session: ThreadSession) -> ExportSuggestion:
        del session
        return ExportSuggestion(target_ratio=DEFAULT_EXPORT_RATIO)
