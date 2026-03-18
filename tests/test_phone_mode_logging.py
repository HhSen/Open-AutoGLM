from phone_agent.phone_mode_logging import (
    append_phone_action_log,
    get_phone_action_log_path,
)


def test_phone_log_path_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAUTOGLM_LOG_DIR", str(tmp_path))

    assert get_phone_action_log_path() == tmp_path / "phone-actions.jsonl"


def test_append_phone_action_log_writes_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAUTOGLM_LOG_DIR", str(tmp_path))

    log_path = append_phone_action_log({"action": "tap", "status": "success"})

    assert log_path == tmp_path / "phone-actions.jsonl"
    assert log_path.exists()
    assert '"action": "tap"' in log_path.read_text(encoding="utf-8")
