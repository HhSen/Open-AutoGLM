from types import SimpleNamespace

from phone_agent.hdc.device import get_current_app


def test_get_current_app_returns_foreground_bundle(monkeypatch):
    monkeypatch.setattr(
        "phone_agent.hdc.device._run_hdc_checked",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                "Mission ID #139\napp name [com.huawei.browser]\nstate #FOREGROUND\n"
            )
        ),
    )

    assert get_current_app() == "com.huawei.browser"


def test_get_current_app_returns_system_home_when_missing(monkeypatch):
    monkeypatch.setattr(
        "phone_agent.hdc.device._run_hdc_checked",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="Mission ID #1\nstate #BACKGROUND\n"
        ),
    )

    assert get_current_app() == "System Home"
