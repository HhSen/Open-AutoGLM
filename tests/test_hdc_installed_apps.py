from phone_agent.hdc.device import _parse_installed_bundle_output


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
