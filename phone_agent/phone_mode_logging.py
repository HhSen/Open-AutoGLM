"""Helpers for persistent CLI phone-mode logging."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

MUTATING_PHONE_ACTIONS = {
    "tap",
    "double-tap",
    "long-press",
    "swipe",
    "type",
    "clear",
    "back",
    "home",
    "launch",
}


def get_phone_action_log_path() -> Path:
    """Return the persistent phone-mode JSONL log path."""
    override = os.getenv("OPENAUTOGLM_LOG_DIR")
    if override:
        return Path(override).expanduser() / "phone-actions.jsonl"

    system = platform.system()
    if system == "Darwin":
        base_dir = Path.home() / "Library" / "Logs" / "OpenAutoGLM"
    elif system == "Windows":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data) / "OpenAutoGLM" / "Logs"
        else:
            base_dir = Path.home() / "AppData" / "Local" / "OpenAutoGLM" / "Logs"
    else:
        xdg_state_home = os.getenv("XDG_STATE_HOME")
        if xdg_state_home:
            base_dir = Path(xdg_state_home) / "open-autoglm"
        else:
            base_dir = Path.home() / ".local" / "state" / "open-autoglm"
        base_dir = base_dir / "logs"

    return base_dir / "phone-actions.jsonl"


def append_phone_action_log(entry: dict[str, Any]) -> Path:
    """Append one JSON log event and return the log file path."""
    log_path = get_phone_action_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
        file_obj.write("\n")
    return log_path


def hash_screenshot_base64(base64_data: str) -> str:
    """Return a stable fingerprint for screenshot bytes."""
    return hashlib.sha256(base64.b64decode(base64_data)).hexdigest()


def assess_state_change(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> dict[str, bool | None]:
    """Compare before/after snapshots for lightweight no-op detection."""
    if not before or not after:
        return {
            "current_app_changed": None,
            "visible_changed": None,
            "likely_no_visible_change": None,
        }

    before_app = before.get("current_app")
    after_app = after.get("current_app")
    before_hash = before.get("screenshot_sha256")
    after_hash = after.get("screenshot_sha256")

    current_app_changed = (
        before_app != after_app
        if before_app is not None and after_app is not None
        else None
    )
    visible_changed = (
        before_hash != after_hash
        if before_hash is not None and after_hash is not None
        else None
    )

    likely_no_visible_change = None
    if current_app_changed is False and visible_changed is False:
        likely_no_visible_change = True
    elif current_app_changed is True or visible_changed is True:
        likely_no_visible_change = False

    return {
        "current_app_changed": current_app_changed,
        "visible_changed": visible_changed,
        "likely_no_visible_change": likely_no_visible_change,
    }
