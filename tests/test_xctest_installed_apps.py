import plistlib

from phone_agent.xctest.device import _parse_installed_apps_plist


def test_parse_installed_apps_plist_extracts_bundle_ids():
    payload = plistlib.dumps(
        [
            {
                "CFBundleIdentifier": "com.apple.Preferences",
                "CFBundleDisplayName": "Settings",
            },
            {"CFBundleIdentifier": "com.apple.mobilesafari"},
            {"CFBundleIdentifier": "com.apple.Preferences"},
        ]
    )

    assert _parse_installed_apps_plist(payload) == [
        "com.apple.Preferences",
        "com.apple.mobilesafari",
    ]
