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

    monkeypatch.setattr(
        main,
        "ensure_phone_control_ready",
        lambda device_type, device_id=None, verbose=True: (
            calls.append(("prepare", device_type.value, device_id, verbose)) or True
        ),
    )
    monkeypatch.setattr(main, "set_device_type", lambda device_type: None)
    monkeypatch.setattr(main, "get_device_factory", lambda: factory)
    monkeypatch.setattr(
        main, "append_phone_action_log", lambda payload: "/tmp/log.jsonl"
    )

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="current-app",
    )

    main.run_direct_phone(args)

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

    main.run_direct_phone(args)

    assert calls == [("adb", "serial-1", "http://localhost:8100")]


def test_run_direct_phone_exits_when_prepare_fails(monkeypatch):
    monkeypatch.setattr(
        main, "ensure_phone_control_ready", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(main, "set_device_type", lambda device_type: None)
    monkeypatch.setattr(main, "get_device_factory", lambda: SimpleNamespace())

    args = argparse.Namespace(
        device_type="adb",
        device_id="serial-1",
        wda_url="http://localhost:8100",
        phone_action="current-app",
    )

    with pytest.raises(SystemExit):
        main.run_direct_phone(args)


def test_run_direct_phone_launch_failure_has_clear_package_hint(monkeypatch, capsys):
    monkeypatch.setattr(
        main,
        "ensure_phone_control_ready",
        lambda device_type, device_id=None, verbose=True: True,
    )
    monkeypatch.setattr(main, "set_device_type", lambda device_type: None)
    monkeypatch.setattr(
        main,
        "get_device_factory",
        lambda: SimpleNamespace(launch_app=lambda *args, **kwargs: False),
    )
    monkeypatch.setattr(
        main, "append_phone_action_log", lambda payload: "/tmp/log.jsonl"
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
        main.run_direct_phone(args)

    captured = capsys.readouterr()
    assert "raw package name or bundle name" in captured.out
