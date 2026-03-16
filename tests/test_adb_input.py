from types import SimpleNamespace

from phone_agent.adb.input import detect_and_set_adb_keyboard, type_text


def test_type_text_skips_empty_input(monkeypatch):
    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called for empty text")

    monkeypatch.setattr("phone_agent.adb.input.subprocess.run", fail_run)

    type_text("")


def test_type_text_uses_base64_broadcast(monkeypatch):
    calls = []

    def fake_run(command, capture_output, text):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("phone_agent.adb.input.subprocess.run", fake_run)

    type_text("sb", device_id="4da988e0")

    assert calls == [
        [
            "adb",
            "-s",
            "4da988e0",
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            "c2I=",
        ]
    ]


def test_detect_and_set_adb_keyboard_does_not_send_empty_warmup(monkeypatch):
    calls = []

    def fake_run(command, capture_output, text):
        calls.append(command)
        if command[-3:] == ["get", "secure", "default_input_method"]:
            return SimpleNamespace(
                returncode=0,
                stdout="com.example.keyboard/.ImeService\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("phone_agent.adb.input.subprocess.run", fake_run)

    original_ime = detect_and_set_adb_keyboard(device_id="4da988e0")

    assert original_ime == "com.example.keyboard/.ImeService"
    assert calls == [
        [
            "adb",
            "-s",
            "4da988e0",
            "shell",
            "settings",
            "get",
            "secure",
            "default_input_method",
        ],
        [
            "adb",
            "-s",
            "4da988e0",
            "shell",
            "ime",
            "set",
            "com.android.adbkeyboard/.AdbIME",
        ],
    ]
