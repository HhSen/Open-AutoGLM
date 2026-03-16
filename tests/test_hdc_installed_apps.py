from phone_agent.hdc.device import _parse_installed_bundle_output, launch_app


def test_parse_installed_bundle_output_extracts_and_sorts():
    output = "\n".join(
        [
            "bundleName: com.tencent.mm",
            "bundle name = com.huawei.camera",
            "bundleName: com.tencent.mm",
        ]
    )

    assert _parse_installed_bundle_output(output) == [
        "com.huawei.camera",
        "com.tencent.mm",
    ]


def test_launch_app_accepts_raw_bundle_name(monkeypatch):
    calls = []

    def fake_run_hdc_checked(hdc_prefix, command, description, **kwargs):
        calls.append((hdc_prefix, command, description, kwargs))

    monkeypatch.setattr("phone_agent.hdc.device._run_hdc_checked", fake_run_hdc_checked)
    monkeypatch.setattr("phone_agent.hdc.device.time.sleep", lambda *_args: None)

    assert launch_app("com.example.raw") is True
    assert calls == [
        (
            ["hdc"],
            [
                "shell",
                "aa",
                "start",
                "-b",
                "com.example.raw",
                "-a",
                "EntryAbility",
            ],
            "launch com.example.raw",
            {"capture_output": True},
        )
    ]
