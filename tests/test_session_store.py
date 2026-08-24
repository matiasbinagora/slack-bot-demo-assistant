from slack_video_assistant.session_store import (
    CanonicalCommand,
    ExportRequest,
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
    assert received.session.pending_export is None
    assert explained.session is not None
    assert explained.session.status is SessionStatus.EXPLANATION_REQUESTED
    assert exported.session is not None
    assert exported.session.status is SessionStatus.EXPORT_PENDING
    assert exported.session.pending_export is not None
    assert exported.session.pending_export.target_ratio == "16:9"
    assert exported.export_request is None
    assert confirmed.session is not None
    assert confirmed.session.status is SessionStatus.CONFIRMATION_CONSUMED
    assert confirmed.session.pending_export is None
    assert confirmed.export_request == ExportRequest(
        key=key,
        file_id="F1",
        target_ratio="16:9",
    )


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
    assert missing.export_request is None
    assert first_export.reason == "export_pending"
    assert duplicate_export.reason == "export_already_pending"
    assert duplicate_export.state_changed is False
    assert duplicate_export.session is not None
    assert duplicate_export.session.pending_export is not None
    assert cancelled.reason == "cancellation_consumed"
    assert cancelled.export_request is None
    assert duplicate_cancel.reason == "nothing_to_cancel"


def test_session_store_blocks_invalid_terminal_and_pending_transitions() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPORT)

    explain_while_pending = store.apply_command(key, CanonicalCommand.EXPLAIN)
    confirm = store.apply_command(key, CanonicalCommand.CONFIRM)
    explain_after_confirm = store.apply_command(key, CanonicalCommand.EXPLAIN)
    export_after_confirm = store.apply_command(key, CanonicalCommand.EXPORT)

    assert explain_while_pending.reason == "export_confirmation_pending"
    assert explain_while_pending.state_changed is False
    assert confirm.reason == "confirmation_consumed"
    assert confirm.export_request == ExportRequest(
        key=key,
        file_id="F1",
        target_ratio="16:9",
    )
    assert explain_after_confirm.reason == "explanation_no_longer_available"
    assert export_after_confirm.reason == "export_no_longer_available"
    assert export_after_confirm.state_changed is False
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CONFIRMATION_CONSUMED
    assert session.pending_export is None


def test_session_store_does_not_reopen_cancelled_sessions() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPORT)
    cancel = store.apply_command(key, CanonicalCommand.CANCEL)
    export_after_cancel = store.apply_command(key, CanonicalCommand.EXPORT)
    explain_after_cancel = store.apply_command(key, CanonicalCommand.EXPLAIN)

    assert cancel.reason == "cancellation_consumed"
    assert export_after_cancel.reason == "export_no_longer_available"
    assert explain_after_cancel.reason == "explanation_no_longer_available"
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.CANCELLATION_CONSUMED
    assert session.pending_export is None


def test_session_store_isolates_pending_export_by_thread() -> None:
    store = ThreadSessionStore()
    first_key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")
    second_key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.2")

    store.receive_video(first_key, file_id="F1")
    store.receive_video(second_key, file_id="F2")
    first_export = store.apply_command(first_key, CanonicalCommand.EXPORT)
    second_confirm = store.apply_command(second_key, CanonicalCommand.CONFIRM)

    assert first_export.reason == "export_pending"
    assert second_confirm.reason == "missing_pending_export"
    first_session = store.get(first_key)
    second_session = store.get(second_key)
    assert first_session is not None
    assert first_session.status is SessionStatus.EXPORT_PENDING
    assert second_session is not None
    assert second_session.status is SessionStatus.VIDEO_RECEIVED


def test_session_store_updates_pending_export_ratio_and_rejects_stale_or_unknown_selection() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPORT)
    bound = store.bind_pending_export_message(key, message_ts="171.1")
    selected = store.select_export_ratio(key, target_ratio="4:3", message_ts="171.1")
    duplicate = store.select_export_ratio(key, target_ratio="4:3", message_ts="171.1")
    stale = store.select_export_ratio(key, target_ratio="3:4", message_ts="171.2")
    invalid = store.select_export_ratio(key, target_ratio="21:9", message_ts="171.1")
    confirmed = store.apply_command(key, CanonicalCommand.CONFIRM)

    assert bound.reason == "export_message_bound"
    assert selected.reason == "export_ratio_selected"
    assert selected.session is not None
    assert selected.session.pending_export is not None
    assert selected.session.pending_export.target_ratio == "4:3"
    assert selected.session.pending_export.message_ts == "171.1"
    assert duplicate.reason == "export_ratio_unchanged"
    assert stale.reason == "stale_pending_export"
    assert invalid.reason == "invalid_ratio"
    assert confirmed.export_request == ExportRequest(
        key=key,
        file_id="F1",
        target_ratio="4:3",
    )


def test_session_store_can_roll_back_failed_explain_start_for_retry() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    store.receive_video(key, file_id="F1")
    explained = store.apply_command(key, CanonicalCommand.EXPLAIN)
    rolled_back = store.rollback_explain_request(key)
    retried = store.apply_command(key, CanonicalCommand.EXPLAIN)

    assert explained.reason == "explanation_requested"
    assert rolled_back.reason == "explanation_rollback"
    assert rolled_back.session is not None
    assert rolled_back.session.status is SessionStatus.VIDEO_RECEIVED
    assert retried.reason == "explanation_requested"
    assert retried.session is not None
    assert retried.session.status is SessionStatus.EXPLANATION_REQUESTED


def test_session_store_cancels_only_active_explanation_jobs() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    store.receive_video(key, file_id="F1")
    explain = store.apply_command(key, CanonicalCommand.EXPLAIN)
    cancel = store.apply_command(key, CanonicalCommand.CANCEL, explanation_cancel_status="accepted")
    duplicate_cancel = store.apply_command(key, CanonicalCommand.CANCEL, explanation_cancel_status="already_requested")
    export_after_cancel = store.apply_command(key, CanonicalCommand.EXPORT)

    assert explain.reason == "explanation_requested"
    assert cancel.reason == "explanation_cancelled"
    assert cancel.session is not None
    assert cancel.session.status is SessionStatus.EXPLANATION_CANCELLED
    assert duplicate_cancel.reason == "explanation_already_cancelled"
    assert export_after_cancel.reason == "export_no_longer_available"


def test_session_store_keeps_requested_explanation_when_cancel_cannot_claim_job() -> None:
    store = ThreadSessionStore()
    key = SessionKey(team_id="T1", channel_id="C1", thread_ts="170.1")

    store.receive_video(key, file_id="F1")
    store.apply_command(key, CanonicalCommand.EXPLAIN)

    publish_won = store.apply_command(key, CanonicalCommand.CANCEL, explanation_cancel_status="publication_started")
    completed_won = store.apply_command(key, CanonicalCommand.CANCEL, explanation_cancel_status="terminal")
    no_job = store.apply_command(key, CanonicalCommand.CANCEL, explanation_cancel_status="missing")

    assert publish_won.reason == "explanation_already_completed"
    assert completed_won.reason == "explanation_already_completed"
    assert no_job.reason == "nothing_to_cancel"
    session = store.get(key)
    assert session is not None
    assert session.status is SessionStatus.EXPLANATION_REQUESTED
