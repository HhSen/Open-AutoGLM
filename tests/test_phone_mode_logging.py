from phone_agent.phone_mode_logging import (
    append_phone_action_log,
    assess_state_change,
    get_phone_action_log_path,
)


def test_phone_log_path_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAUTOGLM_LOG_DIR", str(tmp_path))

    assert get_phone_action_log_path() == tmp_path / "phone-actions.jsonl"


def test_assess_state_change_detects_no_visible_change():
    result = assess_state_change(
        {"current_app": "Settings", "screenshot_sha256": "before"},
        {"current_app": "Settings", "screenshot_sha256": "before"},
    )

    assert result["current_app_changed"] is False
    assert result["visible_changed"] is False
    assert result["likely_no_visible_change"] is True


def test_append_phone_action_log_writes_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAUTOGLM_LOG_DIR", str(tmp_path))

    log_path = append_phone_action_log({"action": "tap", "status": "success"})

    assert log_path == tmp_path / "phone-actions.jsonl"
    assert log_path.exists()
    assert '"action": "tap"' in log_path.read_text(encoding="utf-8")
