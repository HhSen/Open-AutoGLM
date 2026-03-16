"""Input utilities for iOS device text input via WebDriverAgent."""

import time


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


def type_text(
    text: str,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    frequency: int = 60,
) -> None:
    """
    Type text into the currently focused input field.

    Args:
        text: The text to type.
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        frequency: Typing frequency (keys per minute). Default is 60.

    Note:
        The input field must be focused before calling this function.
        Use tap() to focus on the input field first.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "wda/keys")

    response = requests.post(
        url,
        json={"value": list(text), "frequency": frequency},
        timeout=30,
        verify=False,
    )
    _ensure_wda_response_ok(response, "text input")


def clear_text(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
) -> None:
    """
    Clear text in the currently focused input field.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.

    Note:
        This sends a clear command to the active element.
        The input field must be focused before calling this function.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "element/active")

    response = requests.get(url, timeout=10, verify=False)
    _ensure_wda_response_ok(response, "read active element")
    data = response.json()
    element_id = data.get("value", {}).get("ELEMENT") or data.get("value", {}).get(
        "element-6066-11e4-a52e-4f735466cecf"
    )

    if element_id:
        clear_url = _get_wda_session_url(
            wda_url, session_id, f"element/{element_id}/clear"
        )
        clear_response = requests.post(clear_url, timeout=10, verify=False)
        _ensure_wda_response_ok(clear_response, "clear active element")
        return

    _clear_with_backspace(wda_url, session_id)


def _clear_with_backspace(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    max_backspaces: int = 100,
) -> None:
    """
    Clear text by sending backspace keys.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        max_backspaces: Maximum number of backspaces to send.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "wda/keys")

    backspace_char = "\u0008"
    response = requests.post(
        url,
        json={"value": [backspace_char] * max_backspaces},
        timeout=10,
        verify=False,
    )
    _ensure_wda_response_ok(response, "clear with backspace")


def send_keys(
    keys: list[str],
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
) -> None:
    """
    Send a sequence of keys.

    Args:
        keys: List of keys to send.
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.

    Example:
        >>> send_keys(["H", "e", "l", "l", "o"])
        >>> send_keys(["\n"])  # Send enter key
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "wda/keys")

    response = requests.post(url, json={"value": keys}, timeout=10, verify=False)
    _ensure_wda_response_ok(response, "send keys")


def press_enter(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    delay: float = 0.5,
) -> None:
    """
    Press the Enter/Return key.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        delay: Delay in seconds after pressing enter.
    """
    send_keys(["\n"], wda_url, session_id)
    time.sleep(delay)


def hide_keyboard(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
) -> None:
    """
    Hide the on-screen keyboard.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
    """
    requests = _require_requests()

    url = f"{wda_url.rstrip('/')}/wda/keyboard/dismiss"

    response = requests.post(url, timeout=10, verify=False)
    _ensure_wda_response_ok(response, "hide keyboard")


def is_keyboard_shown(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
) -> bool:
    """
    Check if the on-screen keyboard is currently shown.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.

    Returns:
        True if keyboard is shown, False otherwise.
    """
    requests = _require_requests()

    url = _get_wda_session_url(wda_url, session_id, "wda/keyboard/shown")

    response = requests.get(url, timeout=5, verify=False)
    _ensure_wda_response_ok(response, "read keyboard visibility")
    data = response.json()
    return data.get("value", False)


def set_pasteboard(
    text: str,
    wda_url: str = "http://localhost:8100",
) -> None:
    """
    Set the device pasteboard (clipboard) content.

    Args:
        text: Text to set in pasteboard.
        wda_url: WebDriverAgent URL.

    Note:
        This can be useful for inputting large amounts of text.
        After setting pasteboard, you can simulate paste gesture.
    """
    requests = _require_requests()

    url = f"{wda_url.rstrip('/')}/wda/setPasteboard"

    response = requests.post(
        url,
        json={"content": text, "contentType": "plaintext"},
        timeout=10,
        verify=False,
    )
    _ensure_wda_response_ok(response, "set pasteboard")


def get_pasteboard(
    wda_url: str = "http://localhost:8100",
) -> str | None:
    """
    Get the device pasteboard (clipboard) content.

    Args:
        wda_url: WebDriverAgent URL.

    Returns:
        Pasteboard content or None if failed.
    """
    requests = _require_requests()

    url = f"{wda_url.rstrip('/')}/wda/getPasteboard"

    response = requests.post(url, timeout=10, verify=False)
    _ensure_wda_response_ok(response, "get pasteboard")
    data = response.json()
    return data.get("value")
