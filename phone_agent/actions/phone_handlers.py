"""
phone_handlers.py — per-device-type handlers for the ``phone`` CLI sub-command.

Each handler encapsulates the setup and action-dispatch logic that was
previously expressed as a large ``if device_type == DeviceType.X`` block
inside ``run_phone`` in ``main.py``.

Hierarchy
---------
PhoneHandler  (abstract base)
├── IOSPhoneHandler
├── ADBPhoneHandler
└── HDCPhoneHandler  (extends ADBPhoneHandler; same action loop, different setup)

Public surface
--------------
``get_phone_handler(device_type, ...)`` — factory that returns the right
handler instance given the resolved ``DeviceType``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from phone_agent.device_factory import DeviceFactory, DeviceType
from phone_agent.phone_mode_logging import write_phone_action_artifact

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class PhoneHandler(ABC):
    """Contract that every device-specific phone handler must satisfy."""

    @abstractmethod
    def setup(self) -> None:
        """Initialise backend connections; raise on hard failure."""

    @abstractmethod
    def run_action(
        self,
        action: str,
        args: argparse.Namespace,
        action_log: dict,
    ) -> None:
        """
        Execute *action* and mutate *action_log* with ``params`` / ``result``.

        Raises on failure; caller is responsible for catching and logging.
        """


# ---------------------------------------------------------------------------
# Helpers shared across handlers
# ---------------------------------------------------------------------------


def _hash_b64(b64_data: str) -> str:
    return hashlib.sha256(base64.b64decode(b64_data)).hexdigest()


class PhoneActionError(RuntimeError):
    """Action failure with an operator-facing correction hint."""

    def __init__(self, message: str, correction: str) -> None:
        super().__init__(message)
        self.correction = correction


def _stringify_output_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _build_preview(text: str, max_chars: int = 1200) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[: max_chars - 24].rstrip() + "\n... [truncated preview]", True


def _print_action_success(
    summary: str,
    *,
    details: dict[str, Any] | None = None,
    preview: str | None = None,
    full_result_file: str | Path | None = None,
) -> None:
    print("STATUS: OK")
    print(f"SUMMARY: {summary}")
    if details:
        for key, value in details.items():
            print(f"{key.upper()}: {_stringify_output_value(value)}")
    if preview:
        print("RESULT_PREVIEW:")
        print(preview)
    if full_result_file:
        print(f"FULL_RESULT_FILE: {full_result_file}")


def _print_labeled_apps(
    identifiers: list[str],
    lookup_label,
    heading: str,
    note: str | None = None,
) -> None:
    lines = [heading]
    for identifier in identifiers:
        label = lookup_label(identifier)
        if label:
            lines.append(f"- {label} ({identifier})")
        else:
            lines.append(f"- {identifier}")
    if note:
        lines.append("")
        lines.append(f"Note: {note}")

    full_text = "\n".join(lines) + "\n"
    preview_lines = lines[:14]
    preview = "\n".join(preview_lines)
    is_truncated = len(lines) > 14
    if is_truncated:
        preview += "\n... [truncated preview]"
    full_result_file = (
        write_phone_action_artifact("list-apps", ".txt", full_text)
        if is_truncated
        else None
    )

    _print_action_success(
        f"Listed {len(identifiers)} installed apps.",
        details={"app_count": len(identifiers)},
        preview=preview,
        full_result_file=full_result_file,
    )


def _print_or_save_state(state: dict, output_path: str | None) -> None:
    from phone_agent.actions.handler import summarize_ui_tree_for_model

    summarized = summarize_ui_tree_for_model(state)
    device_info = summarized.pop("device_info", None)
    payload = json.dumps(summarized, ensure_ascii=False, indent=2)
    full_payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    preview, is_truncated = _build_preview(payload)
    full_result_file: Path | None = None

    if output_path:
        full_result_file = Path(output_path).expanduser()
        full_result_file.parent.mkdir(parents=True, exist_ok=True)
        full_result_file.write_text(full_payload, encoding="utf-8")
    elif is_truncated:
        full_result_file = write_phone_action_artifact("state", ".json", full_payload)

    details: dict[str, Any] = {
        "node_count": summarized.get("node_count"),
        "truncated": summarized.get("truncated"),
    }
    if isinstance(device_info, dict) and device_info:
        details["device_info"] = device_info

    _print_action_success(
        "Captured current device state.",
        details=details,
        preview=preview,
        full_result_file=full_result_file,
    )


# ---------------------------------------------------------------------------
# iOS handler
# ---------------------------------------------------------------------------


class IOSPhoneHandler(PhoneHandler):
    """Delegates all actions to the ``phone_agent.xctest`` module via WDA."""

    def __init__(self, wda_url: str, device_id: str | None) -> None:
        self.wda_url = wda_url
        self.device_id = device_id
        self._session_id: str | None = None

    # ------------------------------------------------------------------
    def setup(self) -> None:
        import phone_agent.xctest as xctest
        from phone_agent.xctest import XCTestConnection

        conn = XCTestConnection(wda_url=self.wda_url)
        if not conn.is_wda_ready(timeout=5):
            raise PhoneActionError(
                f"WebDriverAgent is not reachable at {self.wda_url}.",
                "Start WebDriverAgent and confirm port forwarding to the configured "
                "`--wda-url`, then rerun the command.",
            )

        ok, session_id = conn.start_wda_session()
        if not ok or not session_id:
            raise PhoneActionError(
                "Failed to create a WebDriverAgent session.",
                "Make sure the iOS device is unlocked, trusted, and visible to WDA, "
                "then retry.",
            )

        self._session_id = session_id
        self._xctest = xctest

    # ------------------------------------------------------------------
    def run_action(
        self,
        action: str,
        args: argparse.Namespace,
        action_log: dict,
    ) -> None:
        import phone_agent.xctest as xctest
        from phone_agent.config.apps_ios import get_app_name as get_ios_app_name

        wda_url = self.wda_url
        session_id = self._session_id
        device_id = self.device_id

        action_log["wda_url"] = wda_url
        action_log["wda_session_id"] = session_id

        if action == "tap":
            xctest.tap(
                args.x,
                args.y,
                wda_url=wda_url,
                session_id=session_id,
                delay=args.delay if args.delay is not None else 1.0,
            )
            _print_action_success(
                "Tap completed.",
                details={"x": args.x, "y": args.y, "delay": args.delay},
            )
            action_log["params"] = {"x": args.x, "y": args.y, "delay": args.delay}

        elif action == "double-tap":
            xctest.double_tap(
                args.x,
                args.y,
                wda_url=wda_url,
                session_id=session_id,
                delay=args.delay if args.delay is not None else 1.0,
            )
            _print_action_success(
                "Double tap completed.",
                details={"x": args.x, "y": args.y, "delay": args.delay},
            )
            action_log["params"] = {"x": args.x, "y": args.y, "delay": args.delay}

        elif action == "long-press":
            xctest.long_press(
                args.x,
                args.y,
                duration=args.duration_ms / 1000.0,
                wda_url=wda_url,
                session_id=session_id,
                delay=args.delay if args.delay is not None else 1.0,
            )
            _print_action_success(
                "Long press completed.",
                details={
                    "x": args.x,
                    "y": args.y,
                    "duration_ms": args.duration_ms,
                    "delay": args.delay,
                },
            )
            action_log["params"] = {
                "x": args.x,
                "y": args.y,
                "duration_ms": args.duration_ms,
                "delay": args.delay,
            }

        elif action == "swipe":
            xctest.swipe(
                args.start_x,
                args.start_y,
                args.end_x,
                args.end_y,
                duration=args.duration_ms / 1000.0 if args.duration_ms else None,
                wda_url=wda_url,
                session_id=session_id,
                delay=args.delay if args.delay is not None else 1.0,
            )
            _print_action_success(
                "Swipe completed.",
                details={
                    "start_x": args.start_x,
                    "start_y": args.start_y,
                    "end_x": args.end_x,
                    "end_y": args.end_y,
                    "duration_ms": args.duration_ms,
                    "delay": args.delay,
                },
            )
            action_log["params"] = {
                "start_x": args.start_x,
                "start_y": args.start_y,
                "end_x": args.end_x,
                "end_y": args.end_y,
                "duration_ms": args.duration_ms,
                "delay": args.delay,
            }

        elif action == "type":
            from phone_agent.xctest.input import type_text as xctest_type

            xctest_type(args.text, wda_url=wda_url, session_id=session_id)
            _print_action_success("Text entered.", details={"text": args.text})
            action_log["params"] = {"text": args.text}

        elif action == "clear":
            from phone_agent.xctest.input import clear_text as xctest_clear

            xctest_clear(wda_url=wda_url, session_id=session_id)
            _print_action_success("Text cleared.")
            action_log["params"] = {}

        elif action == "back":
            xctest.back(
                wda_url=wda_url,
                session_id=session_id,
                delay=args.delay if args.delay is not None else 1.0,
            )
            _print_action_success(
                "Back navigation completed.", details={"delay": args.delay}
            )
            action_log["params"] = {"delay": args.delay}

        elif action == "home":
            xctest.home(
                wda_url=wda_url,
                session_id=session_id,
                delay=args.delay if args.delay is not None else 1.0,
            )
            _print_action_success(
                "Returned to the home screen.", details={"delay": args.delay}
            )
            action_log["params"] = {"delay": args.delay}

        elif action == "launch":
            success = xctest.launch_app(
                args.app_name,
                wda_url=wda_url,
                session_id=session_id,
                delay=args.delay if args.delay is not None else 1.0,
            )
            if success:
                _print_action_success(
                    "App launch completed.",
                    details={"app_name": args.app_name, "delay": args.delay},
                )
                action_log["params"] = {
                    "app_name": args.app_name,
                    "delay": args.delay,
                }
            else:
                raise PhoneActionError(
                    f"Could not launch app '{args.app_name}'.",
                    "Run `phone-use phone list-apps` to inspect installed apps. If the "
                    "app is missing from the registry map, pass its raw bundle id.",
                )

        elif action == "screenshot":
            from phone_agent.xctest.screenshot import (
                get_screenshot as xctest_screenshot,
            )

            shot = xctest_screenshot(
                wda_url=wda_url, session_id=session_id, device_id=device_id
            )
            png_bytes = base64.b64decode(shot.base64_data)
            output_path = os.path.abspath(os.path.expanduser(args.output))
            with open(output_path, "wb") as fh:
                fh.write(png_bytes)
            _print_action_success(
                "Screenshot captured.",
                details={"width": shot.width, "height": shot.height},
                full_result_file=output_path,
            )
            action_log["params"] = {"output": args.output}
            action_log["result"] = {
                "output": output_path,
                "width": shot.width,
                "height": shot.height,
                "screenshot_sha256": _hash_b64(shot.base64_data),
            }

        elif action == "current-app":
            app = xctest.get_current_app(wda_url=wda_url, session_id=session_id)
            _print_action_success(
                "Read the current foreground app.", details={"current_app": app}
            )
            action_log["result"] = {"current_app": app}

        elif action == "list-apps":
            bundle_ids = xctest.list_installed_apps(device_id=device_id)
            _print_labeled_apps(
                bundle_ids,
                get_ios_app_name,
                "Installed iOS apps:",
                "labels from `phone_agent/config/apps_ios.py` are shown when known; "
                "otherwise the bundle id is printed.",
            )
            action_log["result"] = {"installed_app_count": len(bundle_ids)}

        elif action == "state":
            shot = xctest.get_screenshot(
                wda_url=wda_url,
                session_id=session_id,
                device_id=device_id,
            )
            state = xctest.get_ui_tree(
                wda_url=wda_url,
                session_id=session_id,
                screen_width=shot.width,
                screen_height=shot.height,
            )
            state["device_info"] = self._get_device_info(shot.width, shot.height)
            _print_or_save_state(state, args.output)
            output_path = (
                os.path.abspath(os.path.expanduser(args.output))
                if args.output
                else None
            )
            action_log["params"] = {"output": args.output}
            action_log["result"] = {
                "device_info": state.get("device_info"),
                "node_count": state.get("node_count"),
                "output": output_path,
            }

    # ------------------------------------------------------------------
    def _get_device_info(
        self, shot_width: int | None = None, shot_height: int | None = None
    ) -> dict[str, str]:
        from phone_agent.xctest import XCTestConnection
        from phone_agent.xctest.device import get_screen_size

        conn = XCTestConnection(wda_url=self.wda_url)
        info: dict[str, str] = {}
        device_info = conn.get_device_info(device_id=self.device_id)

        if device_info:
            if device_info.device_name:
                info["Device"] = device_info.device_name
            if device_info.model:
                info["Model"] = device_info.model
            if device_info.ios_version:
                info["iOS version"] = device_info.ios_version

        if shot_width and shot_height:
            info["Physical size"] = f"{shot_width}x{shot_height}"

        logical_width: int | None = None
        logical_height: int | None = None
        try:
            logical_width, logical_height = get_screen_size(
                wda_url=self.wda_url, session_id=self._session_id
            )
        except Exception:
            pass

        if logical_width and logical_height:
            info["Logical size"] = f"{logical_width}x{logical_height}"

        return info


# ---------------------------------------------------------------------------
# ADB handler  (also serves as the base for HDC)
# ---------------------------------------------------------------------------


class ADBPhoneHandler(PhoneHandler):
    """Delegates actions to the ``DeviceFactory`` (ADB backend)."""

    _device_type: DeviceType = DeviceType.ADB

    def __init__(self, device_id: str | None) -> None:
        self.device_id = device_id
        self._factory: DeviceFactory | None = None

    @property
    def factory(self) -> DeviceFactory:
        """Return the device factory, raising if ``setup()`` was never called."""
        if self._factory is None:
            raise RuntimeError(
                f"{type(self).__name__}.setup() must be called before using the handler."
            )
        return self._factory

    # ------------------------------------------------------------------
    def setup(self) -> None:

        from phone_agent.adb.input import ensure_adb_keyboard_ready
        from phone_agent.device_factory import get_device_factory, set_device_type

        set_device_type(self._device_type)

        try:
            _, _ = ensure_adb_keyboard_ready(device_id=self.device_id)
        except Exception as exc:
            raise PhoneActionError(
                str(exc),
                "Run `phone-use phone doctor` after installing and enabling ADB Keyboard "
                "to verify device prerequisites.",
            )

        self._factory = get_device_factory()

    # ------------------------------------------------------------------
    def run_action(
        self,
        action: str,
        args: argparse.Namespace,
        action_log: dict,
    ) -> None:
        from phone_agent.config.apps import get_app_name as get_android_app_name

        factory = self.factory
        device_id = self.device_id

        if action == "tap":
            factory.tap(args.x, args.y, device_id=device_id, delay=args.delay)
            _print_action_success(
                "Tap completed.",
                details={"x": args.x, "y": args.y, "delay": args.delay},
            )
            action_log["params"] = {"x": args.x, "y": args.y, "delay": args.delay}

        elif action == "double-tap":
            factory.double_tap(args.x, args.y, device_id=device_id, delay=args.delay)
            _print_action_success(
                "Double tap completed.",
                details={"x": args.x, "y": args.y, "delay": args.delay},
            )
            action_log["params"] = {"x": args.x, "y": args.y, "delay": args.delay}

        elif action == "long-press":
            factory.long_press(
                args.x,
                args.y,
                duration_ms=args.duration_ms,
                device_id=device_id,
                delay=args.delay,
            )
            _print_action_success(
                "Long press completed.",
                details={
                    "x": args.x,
                    "y": args.y,
                    "duration_ms": args.duration_ms,
                    "delay": args.delay,
                },
            )
            action_log["params"] = {
                "x": args.x,
                "y": args.y,
                "duration_ms": args.duration_ms,
                "delay": args.delay,
            }

        elif action == "swipe":
            factory.swipe(
                args.start_x,
                args.start_y,
                args.end_x,
                args.end_y,
                duration_ms=args.duration_ms,
                device_id=device_id,
                delay=args.delay,
            )
            _print_action_success(
                "Swipe completed.",
                details={
                    "start_x": args.start_x,
                    "start_y": args.start_y,
                    "end_x": args.end_x,
                    "end_y": args.end_y,
                    "duration_ms": args.duration_ms,
                    "delay": args.delay,
                },
            )
            action_log["params"] = {
                "start_x": args.start_x,
                "start_y": args.start_y,
                "end_x": args.end_x,
                "end_y": args.end_y,
                "duration_ms": args.duration_ms,
                "delay": args.delay,
            }

        elif action == "type":
            factory.type_text(args.text, device_id=device_id)
            _print_action_success("Text entered.", details={"text": args.text})
            action_log["params"] = {"text": args.text}

        elif action == "clear":
            factory.clear_text(device_id=device_id)
            _print_action_success("Text cleared.")
            action_log["params"] = {}

        elif action == "back":
            factory.back(device_id=device_id, delay=args.delay)
            _print_action_success(
                "Back navigation completed.", details={"delay": args.delay}
            )
            action_log["params"] = {"delay": args.delay}

        elif action == "home":
            factory.home(device_id=device_id, delay=args.delay)
            _print_action_success(
                "Returned to the home screen.", details={"delay": args.delay}
            )
            action_log["params"] = {"delay": args.delay}

        elif action == "launch":
            success = factory.launch_app(
                args.app_name, device_id=device_id, delay=args.delay
            )
            if success:
                _print_action_success(
                    "App launch completed.",
                    details={"app_name": args.app_name, "delay": args.delay},
                )
                action_log["params"] = {
                    "app_name": args.app_name,
                    "delay": args.delay,
                }
            else:
                dt = args.device_type
                raise PhoneActionError(
                    f"Could not launch app '{args.app_name}'.",
                    f"Run `python main.py --device-type {dt} phone list-apps` to inspect "
                    "installed apps. If the app is not in the registry map, pass its raw "
                    "package name or bundle name instead of a numeric index.",
                )

        elif action == "screenshot":
            shot = factory.get_screenshot(device_id=device_id)
            png_bytes = base64.b64decode(shot.base64_data)
            output_path = os.path.abspath(os.path.expanduser(args.output))
            with open(output_path, "wb") as fh:
                fh.write(png_bytes)
            _print_action_success(
                "Screenshot captured.",
                details={"width": shot.width, "height": shot.height},
                full_result_file=output_path,
            )
            action_log["params"] = {"output": args.output}
            action_log["result"] = {
                "output": output_path,
                "width": shot.width,
                "height": shot.height,
                "screenshot_sha256": _hash_b64(shot.base64_data),
            }

        elif action == "current-app":
            app = factory.get_current_app(device_id=device_id)
            _print_action_success(
                "Read the current foreground app.", details={"current_app": app}
            )
            action_log["result"] = {"current_app": app}

        elif action == "list-apps":
            packages = factory.list_installed_apps(device_id=device_id)
            _print_labeled_apps(
                packages,
                get_android_app_name,
                "Installed Android apps:",
                "labels from `phone_agent/config/apps.py` are shown when known; "
                "otherwise the package name is printed.",
            )
            action_log["result"] = {"installed_app_count": len(packages)}

        elif action == "state":
            shot = factory.get_screenshot(device_id=device_id)
            state = factory.get_ui_tree(
                device_id=device_id,
                screen_width=shot.width,
                screen_height=shot.height,
            )
            state["device_info"] = self._get_device_info()
            _print_or_save_state(state, args.output)
            output_path = (
                os.path.abspath(os.path.expanduser(args.output))
                if args.output
                else None
            )
            action_log["params"] = {"output": args.output}
            action_log["result"] = {
                "device_info": state.get("device_info"),
                "node_count": state.get("node_count"),
                "output": output_path,
            }

    # ------------------------------------------------------------------
    def _get_device_info(self) -> dict[str, str]:
        import subprocess

        def _run(cmd: list[str], timeout: int = 5) -> str | None:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=timeout,
                )
            except Exception:
                return None
            return result.stdout.strip() if result.returncode == 0 else None

        def _prefixed(output: str | None, prefix: str) -> str | None:
            if not output:
                return None
            for line in output.splitlines():
                line = line.strip()
                if line.startswith(prefix):
                    return line.split(":", 1)[1].strip()
            return None

        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])

        info: dict[str, str] = {}
        model = _run(cmd + ["shell", "getprop", "ro.product.model"])
        manufacturer = _run(cmd + ["shell", "getprop", "ro.product.manufacturer"])
        android_version = _run(cmd + ["shell", "getprop", "ro.build.version.release"])
        physical_size = _prefixed(_run(cmd + ["shell", "wm", "size"]), "Physical size")
        density = _prefixed(_run(cmd + ["shell", "wm", "density"]), "Physical density")

        if manufacturer and model:
            info["Device"] = f"{manufacturer} {model}"
        elif model:
            info["Device"] = model
        if android_version:
            info["Android version"] = android_version
        if physical_size:
            info["Physical size"] = physical_size
        if density:
            info["Physical density"] = density

        return info


# ---------------------------------------------------------------------------
# HDC handler
# ---------------------------------------------------------------------------


class HDCPhoneHandler(ADBPhoneHandler):
    """
    HarmonyOS variant — same action loop as ADB but:
    - ``state`` action is not supported
    - ``list-apps`` uses the HarmonyOS app-name registry
    - ``setup`` activates HDC verbose=False and skips ADB Keyboard
    """

    _device_type: DeviceType = DeviceType.HDC

    # ------------------------------------------------------------------
    def setup(self) -> None:
        from phone_agent.device_factory import get_device_factory, set_device_type
        from phone_agent.hdc import set_hdc_verbose

        set_device_type(self._device_type)
        set_hdc_verbose(False)
        self._factory = get_device_factory()

    # ------------------------------------------------------------------
    def run_action(
        self,
        action: str,
        args: argparse.Namespace,
        action_log: dict,
    ) -> None:
        if action == "state":
            raise PhoneActionError(
                "The `state` action is not supported for HDC devices.",
                "Use `--device-type adb` or `--device-type ios` for `phone state`, or "
                "switch to another supported action on HDC.",
            )

        if action == "list-apps":
            from phone_agent.config.apps_harmonyos import (
                get_app_name as get_harmony_app_name,
            )

            packages = self.factory.list_installed_apps(device_id=self.device_id)
            _print_labeled_apps(
                packages,
                get_harmony_app_name,
                "Installed HarmonyOS apps:",
                "labels from `phone_agent/config/apps_harmonyos.py` are shown when known; "
                "otherwise the bundle name is printed.",
            )
            action_log["result"] = {"installed_app_count": len(packages)}
            return

        # All other actions share the ADB action loop exactly.
        super().run_action(action, args, action_log)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_phone_handler(
    device_type: DeviceType,
    *,
    device_id: str | None = None,
    wda_url: str = "http://localhost:8100",
) -> PhoneHandler:
    """Return the correct ``PhoneHandler`` for *device_type*."""
    if device_type == DeviceType.IOS:
        return IOSPhoneHandler(wda_url=wda_url, device_id=device_id)
    if device_type == DeviceType.HDC:
        return HDCPhoneHandler(device_id=device_id)
    return ADBPhoneHandler(device_id=device_id)
