from phone_agent.adb.device import _parse_installed_package_output


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
