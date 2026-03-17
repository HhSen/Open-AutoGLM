import sys

import main


def test_parse_phone_args_with_device_id_after_action(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["phone-use", "phone", "tap", "440", "190", "--device-id", "emulator-5554"],
    )

    args = main.parse_args()

    assert args.command == "phone"
    assert args.phone_action == "tap"
    assert args.x == 440
    assert args.y == 190
    assert args.device_id == "emulator-5554"


def test_parse_phone_args_with_device_flags_mixed_positions(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phone-use",
            "--device-type",
            "adb",
            "phone",
            "tap",
            "440",
            "190",
            "--wda-url",
            "http://localhost:8100",
            "-d",
            "emulator-5554",
        ],
    )

    args = main.parse_args()

    assert args.command == "phone"
    assert args.phone_action == "tap"
    assert args.device_type == "adb"
    assert args.device_id == "emulator-5554"
    assert args.wda_url == "http://localhost:8100"


def test_parse_phone_state_args(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["phone-use", "phone", "state", "--output", "state.json"],
    )

    args = main.parse_args()

    assert args.command == "phone"
    assert args.phone_action == "state"
    assert args.output == "state.json"


def test_parse_phone_list_apps_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["phone-use", "phone", "list-apps"])

    args = main.parse_args()

    assert args.command == "phone"
    assert args.phone_action == "list-apps"


def test_parse_phone_prepare_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["phone-use", "phone", "prepare"])

    args = main.parse_args()

    assert args.command == "phone"
    assert args.phone_action == "prepare"


def test_parse_phone_doctor_args_with_device_flag(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["phone-use", "phone", "doctor", "--device-id", "emulator-5554"],
    )

    args = main.parse_args()

    assert args.command == "phone"
    assert args.phone_action == "doctor"
    assert args.device_id == "emulator-5554"
