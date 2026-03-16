from phone_agent.xctest.device import get_current_app


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_get_current_app_returns_bundle_id(monkeypatch):
    class _Requests:
        @staticmethod
        def get(*args, **kwargs):
            return _Response(200, {"value": {"bundleId": "com.apple.mobilesafari"}})

    monkeypatch.setitem(__import__("sys").modules, "requests", _Requests)

    assert get_current_app() == "com.apple.mobilesafari"


def test_get_current_app_returns_system_home_without_bundle(monkeypatch):
    class _Requests:
        @staticmethod
        def get(*args, **kwargs):
            return _Response(200, {"value": {}})

    monkeypatch.setitem(__import__("sys").modules, "requests", _Requests)

    assert get_current_app() == "System Home"
