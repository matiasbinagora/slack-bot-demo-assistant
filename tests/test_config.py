from slack_video_assistant.config import ClaudeSettings, ConfigError, SlackSettings


def test_loads_valid_slack_settings() -> None:
    settings = SlackSettings.from_env(
        {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_APP_TOKEN": "xapp-test-token",
            "LOG_LEVEL": "debug",
            "MAX_VIDEO_BYTES": "2048",
            "MAX_VIDEO_DURATION_SECONDS": "120",
            "VIDEO_TEMP_DIR": "/tmp/slack-video-assistant-tests",
        }
    )

    assert settings.bot_token == "xoxb-test-token"
    assert settings.app_token == "xapp-test-token"
    assert settings.log_level == "DEBUG"
    assert settings.max_video_bytes == 2048
    assert settings.max_video_duration_seconds == 120
    assert str(settings.video_temp_dir) == "/tmp/slack-video-assistant-tests"


def test_missing_bot_token_is_reported_safely() -> None:
    try:
        SlackSettings.from_env({"SLACK_APP_TOKEN": "xapp-test-token"})
    except ConfigError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ConfigError")

    assert "SLACK_BOT_TOKEN" in message
    assert "xapp-test-token" not in message
    assert "http" not in message


def test_missing_app_token_is_reported_safely() -> None:
    try:
        SlackSettings.from_env({"SLACK_BOT_TOKEN": "xoxb-test-token"})
    except ConfigError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ConfigError")

    assert "SLACK_APP_TOKEN" in message
    assert "xoxb-test-token" not in message
    assert "http" not in message


def test_invalid_max_video_bytes_is_reported_safely() -> None:
    try:
        SlackSettings.from_env(
            {
                "SLACK_BOT_TOKEN": "xoxb-test-token",
                "SLACK_APP_TOKEN": "xapp-test-token",
                "MAX_VIDEO_BYTES": "abc",
            }
        )
    except ConfigError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ConfigError")

    assert message == "MAX_VIDEO_BYTES must be an integer."


def test_invalid_max_video_duration_seconds_is_reported_safely() -> None:
    try:
        SlackSettings.from_env(
            {
                "SLACK_BOT_TOKEN": "xoxb-test-token",
                "SLACK_APP_TOKEN": "xapp-test-token",
                "MAX_VIDEO_DURATION_SECONDS": "abc",
            }
        )
    except ConfigError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ConfigError")

    assert message == "MAX_VIDEO_DURATION_SECONDS must be an integer."


def test_loads_valid_claude_settings() -> None:
    settings = ClaudeSettings.from_env({"ANTHROPIC_API_KEY": "sk-ant-test-key"})

    assert settings.api_key == "sk-ant-test-key"


def test_missing_claude_api_key_is_reported_safely() -> None:
    try:
        ClaudeSettings.from_env({})
    except ConfigError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ConfigError")

    assert "ANTHROPIC_API_KEY" in message
    assert "sk-ant" not in message
    assert "http" not in message
