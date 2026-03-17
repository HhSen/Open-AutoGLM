"""Device control utilities for Android automation."""

import os
import re
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET

from phone_agent.config.apps import APP_PACKAGES, get_app_name
from phone_agent.config.timing import TIMING_CONFIG


def _run_adb_command(
    adb_prefix: list[str], command: list[str], description: str
) -> subprocess.CompletedProcess:
    """Run an ADB command and raise if it fails."""
    result = subprocess.run(
        adb_prefix + command,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise ValueError(output or f"ADB {description} failed")
    return result


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently focused app name.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The focused package name when available.
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = _run_adb_command(adb_prefix, ["shell", "dumpsys", "window"], "dumpsys")
    output = result.stdout
    if not output:
        raise ValueError("No output from dumpsys window")

    package_name = _extract_focused_package(output)
    if not package_name:
        return "System Home"

    return get_app_name(package_name) or package_name


def list_installed_apps(device_id: str | None = None) -> list[str]:
    """List installed Android package names from the connected device."""
    adb_prefix = _get_adb_prefix(device_id)
    result = _run_adb_command(
        adb_prefix,
        ["shell", "pm", "list", "packages"],
        "list installed apps",
    )
    return _parse_installed_package_output(result.stdout)


def _parse_installed_package_output(output: str) -> list[str]:
    """Parse `pm list packages` output into sorted package names."""
    packages: set[str] = set()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("package:"):
            line = line[len("package:") :]
        package_name = line.strip()
        if package_name:
            packages.add(package_name)
    return sorted(packages)


def get_ui_tree(
    device_id: str | None = None,
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> dict:
    """Dump the Android UI hierarchy and normalize visible node positions."""
    adb_prefix = _get_adb_prefix(device_id)
    remote_path = f"/sdcard/window_dump_{uuid.uuid4().hex}.xml"
    local_path = os.path.join(
        tempfile.gettempdir(), f"window_dump_{uuid.uuid4().hex}.xml"
    )

    try:
        _run_adb_command(
            adb_prefix,
            ["shell", "uiautomator", "dump", remote_path],
            "uiautomator dump",
        )

        _run_adb_command(adb_prefix, ["pull", remote_path, local_path], "pull UI tree")

        tree = ET.parse(local_path)
        root = tree.getroot()
        nodes = _extract_android_ui_nodes(root, screen_width, screen_height)
        return {
            "source": "adb_uiautomator",
            "node_count": len(nodes),
            "nodes": nodes,
        }
    finally:
        subprocess.run(
            adb_prefix + ["shell", "rm", remote_path],
            capture_output=True,
            text=True,
        )
        if os.path.exists(local_path):
            os.remove(local_path)


def _extract_focused_package(output: str) -> str | None:
    """Extract the currently focused package from dumpsys window output."""
    focus_markers = ("mFocusedApp", "mCurrentFocus")

    for marker in focus_markers:
        for line in output.splitlines():
            if marker not in line:
                continue

            package_name = _extract_package_name(line)
            if package_name:
                return package_name

    return None


def _extract_package_name(line: str) -> str | None:
    """Extract a package name from a single dumpsys output line."""
    match = re.search(r"\s([A-Za-z0-9_.]+)/(?:[A-Za-z0-9_.$]+)", line)
    if match:
        return match.group(1)

    match = re.search(r"\s([A-Za-z0-9_.]+)\}", line)
    if match:
        return match.group(1)

    return None


def _extract_android_ui_nodes(
    root: ET.Element,
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> list[dict]:
    """Flatten visible Android UI nodes and attach normalized bounds."""
    nodes: list[dict] = []
    for index, node in enumerate(root.iter("node")):
        bounds = _parse_android_bounds(node.attrib.get("bounds", ""))
        if bounds is None:
            continue

        normalized = _normalize_bounds(bounds, screen_width, screen_height)
        entry = {
            "index": index,
            "class_name": node.attrib.get("class", ""),
            "resource_id": node.attrib.get("resource-id", ""),
            "text": node.attrib.get("text", ""),
            "content_desc": node.attrib.get("content-desc", ""),
            "package": node.attrib.get("package", ""),
            "clickable": node.attrib.get("clickable") == "true",
            "enabled": node.attrib.get("enabled") == "true",
            "focused": node.attrib.get("focused") == "true",
            "selected": node.attrib.get("selected") == "true",
            **normalized,
        }
        if _should_keep_android_node(entry):
            nodes.append(entry)
    return nodes


def _parse_android_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    """Parse Android uiautomator bounds strings like [0,1][2,3]."""
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        return None
    left, top, right, bottom = match.groups()
    return int(left), int(top), int(right), int(bottom)


def _normalize_bounds(
    bounds: tuple[int, int, int, int],
    screen_width: int | None,
    screen_height: int | None,
) -> dict:
    """Convert absolute bounds into a reusable payload with centers."""
    left, top, right, bottom = bounds
    center_x = int((left + right) / 2)
    center_y = int((top + bottom) / 2)
    result = {
        "bounds_px": [left, top, right, bottom],
        "center_px": [center_x, center_y],
    }

    if screen_width and screen_height:
        result["bounds_rel"] = [
            int(left / screen_width * 1000),
            int(top / screen_height * 1000),
            int(right / screen_width * 1000),
            int(bottom / screen_height * 1000),
        ]
        result["center_rel"] = [
            int(center_x / screen_width * 1000),
            int(center_y / screen_height * 1000),
        ]

    return result


def _should_keep_android_node(node: dict) -> bool:
    """Keep visible Android nodes that carry text, ids, or can be interacted with."""
    left, top, right, bottom = node["bounds_px"]
    has_area = right > left and bottom > top
    has_identity = any([node["text"], node["content_desc"], node["resource_id"]])
    is_interactive = any([node["clickable"], node["focused"], node["selected"]])
    return has_area and (has_identity or is_interactive)


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(adb_prefix, ["shell", "input", "tap", str(x), str(y)], "tap")
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after double tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(adb_prefix, ["shell", "input", "tap", str(x), str(y)], "tap")
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    _run_adb_command(adb_prefix, ["shell", "input", "tap", str(x), str(y)], "tap")
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Long press at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration_ms: Duration of press in milliseconds.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after long press. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(
        adb_prefix,
        ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        "long press",
    )
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Swipe from start to end coordinates.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of swipe in milliseconds (auto-calculated if None).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after swipe. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = _get_adb_prefix(device_id)

    if duration_ms is None:
        # Calculate duration based on distance
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))  # Clamp between 1000-2000ms

    _run_adb_command(
        adb_prefix,
        [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ],
        "swipe",
    )
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the back button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing back. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(adb_prefix, ["shell", "input", "keyevent", "4"], "back")
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing home. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(
        adb_prefix,
        ["shell", "input", "keyevent", "KEYCODE_HOME"],
        "home",
    )
    time.sleep(delay)


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    Launch an app by name.

    Args:
        app_name: The app label from APP_PACKAGES or a raw Android package name.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        True if the launch command was issued, False if the input is empty.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    package = APP_PACKAGES.get(app_name, app_name.strip())
    if not package or package.isdigit():
        return False

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb_command(
        adb_prefix,
        [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        f"launch {package}",
    )
    time.sleep(delay)
    return True


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
