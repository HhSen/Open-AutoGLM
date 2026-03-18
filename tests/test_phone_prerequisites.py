import argparse
from types import SimpleNamespace

import pytest

import main


def test_run_direct_phone_prepares_adb_before_command(monkeypatch):
    calls = []

    factory = SimpleNamespace(
        get_current_app=lambda device_id=None: (
            calls.append(("current-app", device_id)) or "Settings"
        )
    )

    # Patch setup internals inside the handlers module (where they are imported).
    monkeypatch.setattr(
        "phone_agent.actions.phone_handlers.ADBPhoneHandler.setup",
        lambda self: (
            calls.append(("prepare", self._device_type.value, self.device_id, False))
            or setattr(self, "_factory", factory)
        ),
    )
    monkeypatch.setattr(
        "phone_agent.phone_mode_logging.append_phone_action_log",
        lambda payload: "/tmp/log.jsonl",
    )

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="current-app",
    )

    main.run_phone(args)

    assert calls == [
        ("prepare", "adb", "serial-1", False),
        ("current-app", "serial-1"),
    ]


def test_run_direct_phone_doctor_dispatches_to_phone_doctor(monkeypatch):
    calls = []

    monkeypatch.setattr(
        main,
        "run_phone_doctor",
        lambda device_type, device_id=None, wda_url="http://localhost:8100": (
            calls.append((device_type.value, device_id, wda_url)) or True
        ),
    )

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="doctor",
    )

    main.run_phone(args)

    assert calls == [("adb", "serial-1", "http://localhost:8100")]


def test_run_direct_phone_exits_when_prepare_fails(monkeypatch):
    # Simulate setup() raising SystemExit (e.g. keyboard not available).
    monkeypatch.setattr(
        "phone_agent.actions.phone_handlers.ADBPhoneHandler.setup",
        lambda self: (_ for _ in ()).throw(SystemExit(1)),
    )

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="current-app",
    )

    with pytest.raises(SystemExit):
        main.run_phone(args)


def test_run_direct_phone_setup_failure_uses_standard_error_output(monkeypatch, capsys):
    monkeypatch.setattr(
        "phone_agent.actions.phone_handlers.ADBPhoneHandler.setup",
        lambda self: (_ for _ in ()).throw(RuntimeError("ADB Keyboard missing")),
    )
    monkeypatch.setattr(
        "phone_agent.phone_mode_logging.append_phone_action_log",
        lambda payload: "/tmp/log.jsonl",
    )

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="current-app",
    )

    with pytest.raises(SystemExit):
        main.run_phone(args)

    captured = capsys.readouterr()
    assert "STATUS: ERROR" in captured.out
    assert "ERROR: ADB Keyboard missing" in captured.out
    assert "ACTION_LOG: /tmp/log.jsonl" in captured.out


def test_run_direct_phone_launch_failure_has_clear_package_hint(monkeypatch, capsys):
    factory = SimpleNamespace(launch_app=lambda *args, **kwargs: False)

    monkeypatch.setattr(
        "phone_agent.actions.phone_handlers.ADBPhoneHandler.setup",
        lambda self: setattr(self, "_factory", factory),
    )
    monkeypatch.setattr(
        "phone_agent.phone_mode_logging.append_phone_action_log",
        lambda payload: "/tmp/log.jsonl",
    )

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="launch",
        app_name="99",
        delay=None,
    )

    with pytest.raises(SystemExit):
        main.run_phone(args)

    captured = capsys.readouterr()
    assert "STATUS: ERROR" in captured.out
    assert "HOW_TO_FIX:" in captured.out
    assert "raw package name or bundle name" in captured.out


def test_run_direct_phone_prints_action_log_path_on_success(monkeypatch, capsys):
    factory = SimpleNamespace(get_current_app=lambda device_id=None: "Settings")

    monkeypatch.setattr(
        "phone_agent.actions.phone_handlers.ADBPhoneHandler.setup",
        lambda self: setattr(self, "_factory", factory),
    )
    monkeypatch.setattr(
        "phone_agent.phone_mode_logging.append_phone_action_log",
        lambda payload: "/tmp/log.jsonl",
    )

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="current-app",
    )

    main.run_phone(args)

    captured = capsys.readouterr()
    assert "STATUS: OK" in captured.out
    assert "SUMMARY: Read the current foreground app." in captured.out
    assert 'CURRENT_APP: "Settings"' in captured.out
    assert "ACTION_LOG: /tmp/log.jsonl" in captured.out
