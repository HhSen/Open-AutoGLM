"""Helpers for persistent CLI phone-mode logging."""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any


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


def get_phone_action_artifact_dir() -> Path:
    """Return the directory used for persisted phone-mode result artifacts."""
    return get_phone_action_log_path().parent / "phone-results"


def write_phone_action_artifact(
    action: str,
    suffix: str,
    payload: str | bytes,
) -> Path:
    """Persist a phone-mode result artifact and return its path."""
    artifact_dir = get_phone_action_artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = artifact_dir / f"{timestamp}-{action}{suffix}"
    if isinstance(payload, bytes):
        artifact_path.write_bytes(payload)
    else:
        artifact_path.write_text(payload, encoding="utf-8")
    return artifact_path


class PhoneActionLogger:
    """Context manager that owns the action-log lifecycle for ``run_phone``.

    Logs only the action inputs and the execution outcome (success or error).
    No device round-trips are made for logging purposes.

    Usage::

        with PhoneActionLogger(action, device_type, device_id) as log:
            handler.run_action(action, args, log.entry)
        # On clean exit the entry is written with status="success".
        # On exception the entry is written with status="error" and the
        # process exits after printing a user-facing message.

    Attributes
    ----------
    entry:
        The mutable log dict.  Action handlers that accept an ``action_log``
        argument may add their own output keys to this reference.
    log_path:
        Set after ``__exit__`` completes; the path where the entry was appended.
    """

    def __init__(
        self,
        action: str,
        device_type_value: str,
        device_id: str | None,
    ) -> None:
        self.entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "command": "phone",
            "action": action,
            "device_type": device_type_value,
            "device_id": device_id,
            "cwd": os.getcwd(),
            "argv": sys.argv,
            "status": "started",
        }
        self.log_path: Path | None = None

    def __enter__(self) -> "PhoneActionLogger":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_type is None:
            self.entry["status"] = "success"
            self.log_path = append_phone_action_log(self.entry)
            return False

        if exc_type is SystemExit:
            exit_code = getattr(exc_val, "code", 1)
            if exit_code not in (0, None) and self.entry.get("status") == "started":
                self.entry["status"] = "error"
                self.entry["error"] = "Command exited before completing successfully."
                self.log_path = append_phone_action_log(self.entry)
                print("STATUS: ERROR")
                print("ERROR: Command exited before completing successfully.")
                print(
                    "HOW_TO_FIX: Run `phone-use phone doctor` to verify device setup, "
                    "then retry the command."
                )
                print(f"ACTION_LOG: {self.log_path}")
                return False

            self.log_path = append_phone_action_log(self.entry)
            return False

        # Unexpected exception — record, surface to the user, then exit cleanly.
        self.entry["status"] = "error"
        self.entry["error"] = str(exc_val)
        self.log_path = append_phone_action_log(self.entry)
        correction = getattr(exc_val, "correction", None)
        print("STATUS: ERROR")
        print(f"ERROR: {exc_val}")
        if correction:
            print(f"HOW_TO_FIX: {correction}")
        else:
            print(
                "HOW_TO_FIX: Run `phone-use phone doctor` to verify device setup, "
                "then retry the command."
            )
        print(f"ACTION_LOG: {self.log_path}")
        sys.exit(1)
