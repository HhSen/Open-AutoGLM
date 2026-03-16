"""Device control utilities for iOS automation via WebDriverAgent."""

import json
import plistlib
import subprocess
import time

from phone_agent.config.apps_ios import APP_PACKAGES_IOS as APP_PACKAGES, get_app_name

SCALE_FACTOR = 3  # 3 for most modern iPhone


def _require_requests():
    try:
        import requests

        return requests
    except ImportError as exc:
        raise ValueError(
            "requests library required. Install: pip install requests"
        ) from exc


def _ensure_wda_response_ok(response, description: str) -> None:
    try:
        response.raise_for_status()
    except Exception as exc:
        body = getattr(response, "text", "")
        detail = body.strip() if isinstance(body, str) else ""
        raise ValueError(detail or f"WDA {description} failed") from exc


def _get_wda_session_url(wda_url: str, session_id: str | None, endpoint: str) -> str:
    """
    Get the correct WDA URL for a session endpoint.

    Args:
        wda_url: Base WDA URL.
        session_id: Optional session ID.
        endpoint: The endpoint path.

    Returns:
        Full URL for the endpoint.
    """
    base = wda_url.rstrip("/")
    if session_id:
        return f"{base}/session/{session_id}/{endpoint}"
    else:
        # Try to use WDA endpoints without session when possible
        return f"{base}/{endpoint}"


def get_current_app(
    wda_url: str = "http://localhost:8100", session_id: str | None = None
) -> str:
    """
    Get the currently active app bundle ID.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.

    Returns:
        The active bundle ID when available.
    """
    requests = _require_requests()

    response = requests.get(
        f"{wda_url.rstrip('/')}/wda/activeAppInfo", timeout=5, verify=False
    )
    _ensure_wda_response_ok(response, "read current app")
    data = response.json()
    value = data.get("value", {})
    bundle_id = value.get("bundleId", "")
    if not bundle_id:
        return "System Home"

    return get_app_name(bundle_id) or bundle_id


def list_installed_apps(device_id: str | None = None) -> list[str]:
    """List installed iOS apps from the connected device."""
    command = ["ideviceinstaller"]
    if device_id:
        command.extend(["-u", device_id])
    command.extend(["-l", "-o", "xml"])

    try:
        result = subprocess.run(command, capture_output=True, timeout=20)
    except FileNotFoundError as exc:
        raise ValueError(
            "ideviceinstaller not found. Install it to list installed iOS apps."
        ) from exc

    if result.returncode != 0:
        output = (result.stderr or result.stdout or b"").decode(
            "utf-8", errors="replace"
        )
        raise ValueError(output.strip() or "Failed to list installed iOS apps")

    return _parse_installed_apps_plist(result.stdout)


def _parse_installed_apps_plist(payload: bytes) -> list[str]:
    """Parse `ideviceinstaller -l -o xml` output into sorted bundle ids."""
    data = plistlib.loads(payload)
    bundle_ids: set[str] = set()

    if not isinstance(data, list):
        return []

    for item in data:
        if not isinstance(item, dict):
            continue

        bundle_id = item.get("CFBundleIdentifier")
        if not isinstance(bundle_id, str) or not bundle_id:
            continue

        bundle_ids.add(bundle_id)

    return sorted(bundle_ids)


def get_ui_tree(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> dict:
    """Fetch the iOS accessibility hierarchy from WebDriverAgent."""
    try:
        import requests

        url = _get_wda_session_url(wda_url, session_id, "source?format=json")
        response = requests.get(url, timeout=15, verify=False)
        response.raise_for_status()

        payload = response.json().get("value")
        if isinstance(payload, str):
            payload = json.loads(payload)

        point_width, point_height = get_screen_size(wda_url, session_id)
        nodes = _extract_ios_ui_nodes(
            payload,
            screen_width,
            screen_height,
            scale_x=(screen_width / point_width)
            if screen_width and point_width
            else None,
            scale_y=(screen_height / point_height)
            if screen_height and point_height
            else None,
        )
        return {
            "source": "wda_source_json",
            "node_count": len(nodes),
            "nodes": nodes,
        }
    except ImportError as exc:
        raise ValueError("requests library required for iOS UI tree support") from exc
    except Exception as exc:
        raise ValueError(f"Failed to fetch iOS UI tree: {exc}") from exc


def tap(
    x: int,
    y: int,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> None:
    """
    Tap at the specified coordinates using WebDriver W3C Actions API.

    Args:
        x: X coordinate.
        y: Y coordinate.
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after tap.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "actions")

    # W3C WebDriver Actions API for tap/click
    actions = {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {
                        "type": "pointerMove",
                        "duration": 0,
                        "x": x / SCALE_FACTOR,
                        "y": y / SCALE_FACTOR,
                    },
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 0.1},
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }

    response = requests.post(url, json=actions, timeout=15, verify=False)
    _ensure_wda_response_ok(response, "tap")
    time.sleep(delay)


def _extract_ios_ui_nodes(
    root: dict | list | None,
    screen_width: int | None = None,
    screen_height: int | None = None,
    scale_x: float | None = None,
    scale_y: float | None = None,
) -> list[dict]:
    """Flatten the iOS accessibility tree into normalized nodes."""
    nodes: list[dict] = []

    def visit(node: dict | list | None, path: str = "0") -> None:
        if isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}.{index}")
            return
        if not isinstance(node, dict):
            return

        rect = node.get("rect") or {}
        normalized = _normalize_ios_rect(
            rect,
            screen_width,
            screen_height,
            scale_x=scale_x,
            scale_y=scale_y,
        )
        entry = {
            "path": path,
            "type": node.get("type") or node.get("elementType") or "",
            "name": node.get("name") or "",
            "label": node.get("label") or "",
            "value": node.get("value") or "",
            "enabled": bool(node.get("enabled", False)),
            "visible": bool(node.get("visible", True)),
            "accessible": bool(node.get("accessible", False)),
            **normalized,
        }
        if _should_keep_ios_node(entry):
            nodes.append(entry)

        for index, child in enumerate(node.get("children") or []):
            visit(child, f"{path}.{index}")

    visit(root)
    return nodes


def _normalize_ios_rect(
    rect: dict,
    screen_width: int | None,
    screen_height: int | None,
    scale_x: float | None = None,
    scale_y: float | None = None,
) -> dict:
    """Normalize an iOS WDA rect into point, pixel, and relative coordinates."""
    x = int(float(rect.get("x", 0)))
    y = int(float(rect.get("y", 0)))
    width = int(float(rect.get("width", 0)))
    height = int(float(rect.get("height", 0)))
    right = x + width
    bottom = y + height
    center_x = x + int(width / 2)
    center_y = y + int(height / 2)

    resolved_scale_x = scale_x or SCALE_FACTOR
    resolved_scale_y = scale_y or SCALE_FACTOR

    result = {
        "bounds_points": [x, y, right, bottom],
        "center_points": [center_x, center_y],
        "bounds_px": [
            int(x * resolved_scale_x),
            int(y * resolved_scale_y),
            int(right * resolved_scale_x),
            int(bottom * resolved_scale_y),
        ],
        "center_px": [
            int(center_x * resolved_scale_x),
            int(center_y * resolved_scale_y),
        ],
    }

    if screen_width and screen_height:
        result["bounds_rel"] = [
            int(result["bounds_px"][0] / screen_width * 1000),
            int(result["bounds_px"][1] / screen_height * 1000),
            int(result["bounds_px"][2] / screen_width * 1000),
            int(result["bounds_px"][3] / screen_height * 1000),
        ]
        result["center_rel"] = [
            int(result["center_px"][0] / screen_width * 1000),
            int(result["center_px"][1] / screen_height * 1000),
        ]

    return result


def _should_keep_ios_node(node: dict) -> bool:
    """Keep visible iOS nodes with identity or interaction semantics."""
    left, top, right, bottom = node["bounds_px"]
    has_area = right > left and bottom > top
    has_identity = any([node["name"], node["label"], node["value"]])
    interactive_types = (
        "Button",
        "Cell",
        "Field",
        "Key",
        "Link",
        "Image",
        "ScrollView",
        "SecureTextField",
        "Slider",
        "StaticText",
        "Switch",
        "TabBar",
        "TextField",
    )
    is_interactive = node["accessible"] or any(
        marker in node["type"] for marker in interactive_types
    )
    return has_area and node["visible"] and (has_identity or is_interactive)


def double_tap(
    x: int,
    y: int,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> None:
    """
    Double tap at the specified coordinates using WebDriver W3C Actions API.

    Args:
        x: X coordinate.
        y: Y coordinate.
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after double tap.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "actions")

    # W3C WebDriver Actions API for double tap
    actions = {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {
                        "type": "pointerMove",
                        "duration": 0,
                        "x": x / SCALE_FACTOR,
                        "y": y / SCALE_FACTOR,
                    },
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerUp", "button": 0},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }

    response = requests.post(url, json=actions, timeout=10, verify=False)
    _ensure_wda_response_ok(response, "double tap")
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration: float = 3.0,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> None:
    """
    Long press at the specified coordinates using WebDriver W3C Actions API.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration: Duration of press in seconds.
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after long press.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "actions")

    # W3C WebDriver Actions API for long press
    # Convert duration to milliseconds
    duration_ms = int(duration * 1000)

    actions = {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {
                        "type": "pointerMove",
                        "duration": 0,
                        "x": x / SCALE_FACTOR,
                        "y": y / SCALE_FACTOR,
                    },
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": duration_ms},
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }

    response = requests.post(
        url, json=actions, timeout=int(duration + 10), verify=False
    )
    _ensure_wda_response_ok(response, "long press")
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration: float | None = None,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> None:
    """
    Swipe from start to end coordinates using WDA dragfromtoforduration endpoint.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration: Duration of swipe in seconds (auto-calculated if None).
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after swipe.
    """
    requests = _require_requests()

    if duration is None:
        # Calculate duration based on distance
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration = dist_sq / 1000000  # Convert to seconds
        duration = max(0.3, min(duration, 2.0))  # Clamp between 0.3-2 seconds

    url = _get_wda_session_url(wda_url, session_id, "wda/dragfromtoforduration")

    # WDA dragfromtoforduration API payload
    payload = {
        "fromX": start_x / SCALE_FACTOR,
        "fromY": start_y / SCALE_FACTOR,
        "toX": end_x / SCALE_FACTOR,
        "toY": end_y / SCALE_FACTOR,
        "duration": duration,
    }

    response = requests.post(
        url, json=payload, timeout=int(duration + 10), verify=False
    )
    _ensure_wda_response_ok(response, "swipe")
    time.sleep(delay)


def back(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> None:
    """
    Navigate back (swipe from left edge).

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after navigation.

    Note:
        iOS doesn't have a universal back button. This simulates a back gesture
        by swiping from the left edge of the screen.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "wda/dragfromtoforduration")

    # Swipe from left edge to simulate back gesture
    payload = {
        "fromX": 0,
        "fromY": 640,
        "toX": 400,
        "toY": 640,
        "duration": 0.3,
    }

    response = requests.post(url, json=payload, timeout=10, verify=False)
    _ensure_wda_response_ok(response, "back gesture")
    time.sleep(delay)


def home(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> None:
    """
    Press the home button.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after pressing home.
    """
    requests = _require_requests()

    url = f"{wda_url.rstrip('/')}/wda/homescreen"

    response = requests.post(url, timeout=10, verify=False)
    _ensure_wda_response_ok(response, "home")
    time.sleep(delay)


def launch_app(
    app_name: str,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> bool:
    """
    Launch an app by name.

    Args:
        app_name: The app name (must be in APP_PACKAGES).
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after launching.

    Returns:
        True if app was launched, False if app not found.
    """
    if app_name not in APP_PACKAGES:
        return False

    requests = _require_requests()

    bundle_id = APP_PACKAGES[app_name]
    url = _get_wda_session_url(wda_url, session_id, "wda/apps/launch")

    response = requests.post(
        url, json={"bundleId": bundle_id}, timeout=10, verify=False
    )
    _ensure_wda_response_ok(response, f"launch {app_name}")
    time.sleep(delay)
    return True


def get_screen_size(
    wda_url: str = "http://localhost:8100", session_id: str | None = None
) -> tuple[int, int]:
    """
    Get the screen dimensions.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.

    Returns:
        Tuple of (width, height). Returns (375, 812) as default if unable to fetch.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "window/size")

    response = requests.get(url, timeout=5, verify=False)
    _ensure_wda_response_ok(response, "read screen size")
    data = response.json()
    value = data.get("value", {})
    width = value.get("width", 375)
    height = value.get("height", 812)
    return width, height


def press_button(
    button_name: str,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 1.0,
) -> None:
    """
    Press a physical button.

    Args:
        button_name: Button name (e.g., "home", "volumeUp", "volumeDown").
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after pressing.
    """
    requests = _require_requests()

    url = f"{wda_url.rstrip('/')}/wda/pressButton"

    response = requests.post(url, json={"name": button_name}, timeout=10, verify=False)
    _ensure_wda_response_ok(response, f"press button {button_name}")
    time.sleep(delay)
