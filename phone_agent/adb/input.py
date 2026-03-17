"""Input utilities for Android device text input."""

import base64
import subprocess


ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"


def _run_adb_command(
    adb_prefix: list[str], command: list[str], description: str
) -> subprocess.CompletedProcess:
    """Run an ADB command and raise if it fails."""
    result = subprocess.run(adb_prefix + command, capture_output=True, text=True)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise ValueError(output or f"ADB {description} failed")
    return result


def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field using ADB Keyboard.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Note:
        Requires ADB Keyboard to be installed on the device.
        See: https://github.com/nicnocquee/AdbKeyboard
    """
    if text == "":
        return

    adb_prefix = _get_adb_prefix(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    _run_adb_command(
        adb_prefix,
        [
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded_text,
        ],
        "text input",
    )


def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(
        adb_prefix,
        ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
        "clear text",
    )


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Detect current keyboard and switch to ADB Keyboard if needed.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The original keyboard IME identifier for later restoration.
    """
    current_ime, _ = ensure_adb_keyboard_ready(device_id=device_id)
    return current_ime


def is_adb_keyboard_installed(device_id: str | None = None) -> bool:
    """Return True when ADB Keyboard is installed on the device."""
    adb_prefix = _get_adb_prefix(device_id)
    result = _run_adb_command(
        adb_prefix,
        ["shell", "ime", "list", "-a"],
        "list input methods",
    )
    return ADB_KEYBOARD_IME in (result.stdout + result.stderr)


def is_adb_keyboard_enabled(device_id: str | None = None) -> bool:
    """Return True when ADB Keyboard is enabled on the device."""
    adb_prefix = _get_adb_prefix(device_id)
    result = _run_adb_command(
        adb_prefix,
        ["shell", "settings", "get", "secure", "enabled_input_methods"],
        "read enabled input methods",
    )
    enabled_imes = (result.stdout + result.stderr).strip()
    return ADB_KEYBOARD_IME in enabled_imes


def get_current_ime(device_id: str | None = None) -> str:
    """Return the current default input method."""
    adb_prefix = _get_adb_prefix(device_id)

    result = _run_adb_command(
        adb_prefix,
        ["shell", "settings", "get", "secure", "default_input_method"],
        "read default input method",
    )
    return (result.stdout + result.stderr).strip()


def ensure_adb_keyboard_ready(device_id: str | None = None) -> tuple[str, bool]:
    """Ensure ADB Keyboard is installed, enabled, and selected."""
    adb_prefix = _get_adb_prefix(device_id)

    if not is_adb_keyboard_installed(device_id=device_id):
        raise ValueError(
            "ADB Keyboard is not installed on the device. "
            "Install it first: https://github.com/senzhk/ADBKeyBoard"
        )

    current_ime = get_current_ime(device_id=device_id)
    changed = False

    if not is_adb_keyboard_enabled(device_id=device_id):
        _run_adb_command(
            adb_prefix,
            ["shell", "ime", "enable", ADB_KEYBOARD_IME],
            "enable ADB keyboard",
        )
        changed = True

    # Switch to ADB Keyboard if not already set
    if ADB_KEYBOARD_IME not in current_ime:
        _run_adb_command(
            adb_prefix,
            ["shell", "ime", "set", ADB_KEYBOARD_IME],
            "set ADB keyboard",
        )
        changed = True

    return current_ime, changed


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore the original keyboard IME.

    Args:
        ime: The IME identifier to restore.
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(adb_prefix, ["shell", "ime", "set", ime], "restore keyboard")


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
