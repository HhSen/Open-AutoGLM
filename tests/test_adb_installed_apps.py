from phone_agent.adb.device import _parse_installed_package_output, launch_app


def test_parse_installed_package_output_strips_prefix_and_sorts():
    output = "\n".join(
        [
            "package:com.google.android.youtube",
            "package:com.tencent.mm",
            "com.example.raw",
            "package:com.google.android.youtube",
            "",
        ]
    )

    assert _parse_installed_package_output(output) == [
        "com.example.raw",
        "com.google.android.youtube",
        "com.tencent.mm",
    ]


def test_launch_app_accepts_raw_package_name(monkeypatch):
    calls = []

    def fake_run_adb_command(adb_prefix, command, description):
        calls.append((adb_prefix, command, description))

    monkeypatch.setattr("phone_agent.adb.device._run_adb_command", fake_run_adb_command)
    monkeypatch.setattr("phone_agent.adb.device.time.sleep", lambda *_args: None)

    assert launch_app("com.example.raw") is True
    assert calls == [
        (
            ["adb"],
            [
                "shell",
                "monkey",
                "-p",
                "com.example.raw",
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            "launch com.example.raw",
        )
    ]
