from slack_video_assistant.session_store import (
    CanonicalCommand,
    SessionKey,
    SessionStatus,
    ThreadSessionStore,
)


def test_session_store_tracks_video_and_canonical_state_transitions() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    received = store.receive_video(key, file_id="F1")
    explained = store.apply_command(key, CanonicalCommand.EXPLAIN)
    exported = store.apply_command(key, CanonicalCommand.EXPORT)
    confirmed = store.apply_command(key, CanonicalCommand.CONFIRM)

    assert received.state_changed is True
    assert received.session is not None
    assert received.session.status is SessionStatus.VIDEO_RECEIVED
    assert explained.session is not None
    assert explained.session.status is SessionStatus.EXPLANATION_REQUESTED
    assert exported.session is not None
    assert exported.session.status is SessionStatus.EXPORT_PENDING
    assert confirmed.session is not None
    assert confirmed.session.status is SessionStatus.CONFIRMATION_CONSUMED


def test_session_store_rejects_out_of_order_confirm_and_duplicate_export() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    missing = store.apply_command(key, CanonicalCommand.CONFIRM)
    store.receive_video(key, file_id="F1")
    first_export = store.apply_command(key, CanonicalCommand.EXPORT)
    duplicate_export = store.apply_command(key, CanonicalCommand.EXPORT)
    cancelled = store.apply_command(key, CanonicalCommand.CANCEL)
    duplicate_cancel = store.apply_command(key, CanonicalCommand.CANCEL)

    assert missing.reason == "missing_session"
    assert first_export.reason == "export_pending"
    assert duplicate_export.reason == "export_already_pending"
    assert duplicate_export.state_changed is False
    assert cancelled.reason == "cancellation_consumed"
    assert duplicate_cancel.reason == "nothing_to_cancel"
