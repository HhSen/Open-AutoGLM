import plistlib

from phone_agent.xctest.device import _parse_installed_apps_plist, launch_app


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


def test_launch_app_accepts_raw_bundle_id(monkeypatch):
    requests_calls = []

    class _Response:
        def raise_for_status(self):
            return None

    class _Requests:
        @staticmethod
        def post(url, json, timeout, verify):
            requests_calls.append((url, json, timeout, verify))
            return _Response()

    monkeypatch.setattr(
        "phone_agent.xctest.device._require_requests", lambda: _Requests
    )
    monkeypatch.setattr("phone_agent.xctest.device.time.sleep", lambda *_args: None)

    assert launch_app("com.example.raw") is True
    assert requests_calls == [
        (
            "http://localhost:8100/wda/apps/launch",
            {"bundleId": "com.example.raw"},
            10,
            False,
        )
    ]
