from types import SimpleNamespace

from phone_agent.adb.device import get_current_app


def test_get_current_app_returns_known_app_name(monkeypatch):
    monkeypatch.setattr(
        "phone_agent.adb.device.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                "mCurrentFocus=Window{aa16a9 u0 "
                "com.google.android.youtube/com.google.android.youtube.app.honeycomb.Shell$HomeActivity}"
            )
        ),
    )

    assert get_current_app() == "com.google.android.youtube"


def test_get_current_app_returns_package_for_unknown_app(monkeypatch):
    monkeypatch.setattr(
        "phone_agent.adb.device.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="mFocusedApp=ActivityRecord{123 u0 com.example.unknown/.MainActivity t1}"
        ),
    )

    assert get_current_app() == "com.example.unknown"


def test_get_current_app_returns_launcher_package(monkeypatch):
    monkeypatch.setattr(
        "phone_agent.adb.device.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                "mFocusedApp=ActivityRecord{134081224 u0 "
                "com.google.android.apps.nexuslauncher/.NexusLauncherActivity t6}"
            )
        ),
    )

    assert get_current_app() == "com.google.android.apps.nexuslauncher"
