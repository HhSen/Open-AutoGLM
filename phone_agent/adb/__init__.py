"""ADB utilities for Android device interaction."""

from phone_agent.adb.connection import (
    ADBConnection,
    ConnectionType,
    DeviceInfo,
    list_devices,
    quick_connect,
)
from phone_agent.adb.device import (
    back,
    double_tap,
    get_current_app,
    get_ui_tree,
    home,
    list_installed_apps,
    launch_app,
    long_press,
    swipe,
    tap,
)
from phone_agent.adb.input import (
    ADB_KEYBOARD_IME,
    clear_text,
    detect_and_set_adb_keyboard,
    ensure_adb_keyboard_ready,
    get_current_ime,
    is_adb_keyboard_enabled,
    is_adb_keyboard_installed,
    restore_keyboard,
    type_text,
)
from phone_agent.adb.screenshot import get_screenshot

__all__ = [
    # Screenshot
    "get_screenshot",
    # Input
    "ADB_KEYBOARD_IME",
    "type_text",
    "clear_text",
    "detect_and_set_adb_keyboard",
    "ensure_adb_keyboard_ready",
    "get_current_ime",
    "is_adb_keyboard_enabled",
    "is_adb_keyboard_installed",
    "restore_keyboard",
    # Device control
    "get_current_app",
    "get_ui_tree",
    "list_installed_apps",
    "tap",
    "swipe",
    "back",
    "home",
    "double_tap",
    "long_press",
    "launch_app",
    # Connection management
    "ADBConnection",
    "DeviceInfo",
    "ConnectionType",
    "quick_connect",
    "list_devices",
]
