from slack_video_assistant.config import ConfigError, SlackSettings


def test_loads_valid_slack_settings() -> None:
    settings = SlackSettings.from_env(
        {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_APP_TOKEN": "xapp-test-token",
            "LOG_LEVEL": "debug",
        }
    )

    assert settings.bot_token == "xoxb-test-token"
    assert settings.app_token == "xapp-test-token"
    assert settings.log_level == "DEBUG"


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
