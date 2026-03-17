#!/usr/bin/env python3
"""
Phone Agent CLI - AI-powered phone automation.

Usage:
    python main.py [OPTIONS] [task]          # agent mode (AI-powered)
    python main.py phone <action> [OPTIONS]  # direct device control (no AI)

Environment Variables:
    PHONE_AGENT_BASE_URL: Model API base URL (default: http://localhost:8000/v1)
    PHONE_AGENT_MODEL: Model name (default: autoglm-phone-9b)
    PHONE_AGENT_API_KEY: API key for model authentication (default: EMPTY)
    PHONE_AGENT_MAX_STEPS: Maximum steps per task (default: 100)
    PHONE_AGENT_DEVICE_ID: ADB device ID for multi-device setups
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from openai import OpenAI

from phone_agent import PhoneAgent
from phone_agent.actions.handler import summarize_ui_tree_for_model
from phone_agent.agent import AgentConfig
from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent
from phone_agent.config.apps import get_app_name as get_android_app_name
from phone_agent.config.apps_harmonyos import get_app_name as get_harmony_app_name
from phone_agent.config.apps_ios import get_app_name as get_ios_app_name
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig
from phone_agent.phone_mode_logging import (
    MUTATING_PHONE_ACTIONS,
    append_phone_action_log,
    assess_state_change,
    hash_screenshot_base64,
)
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices


def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB,
    wda_url: str = "http://localhost:8100",
    device_id: str | None = None,
) -> bool:
    """
    Check system requirements before running the agent.

    Checks:
    1. ADB/HDC/iOS tools installed
    2. At least one device connected
    3. ADB Keyboard installed on the device (for ADB only)
    4. WebDriverAgent running (for iOS only)

    Args:
        device_type: Type of device tool (ADB, HDC, or IOS).
        wda_url: WebDriverAgent URL (for iOS only).

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking system requirements...")
    print("-" * 50)

    all_passed = True

    # Determine tool name and command
    if device_type == DeviceType.IOS:
        tool_name = "libimobiledevice"
        tool_cmd = "idevice_id"
    else:
        tool_name = "ADB" if device_type == DeviceType.ADB else "HDC"
        tool_cmd = "adb" if device_type == DeviceType.ADB else "hdc"

    # Check 1: Tool installed
    print(f"1. Checking {tool_name} installation...", end=" ")
    if shutil.which(tool_cmd) is None:
        print("❌ FAILED")
        print(f"   Error: {tool_name} is not installed or not in PATH.")
        print(f"   Solution: Install {tool_name}:")
        if device_type == DeviceType.ADB:
            print("     - macOS: brew install android-platform-tools")
            print("     - Linux: sudo apt install android-tools-adb")
            print(
                "     - Windows: Download from https://developer.android.com/studio/releases/platform-tools"
            )
        elif device_type == DeviceType.HDC:
            print(
                "     - Download from HarmonyOS SDK or https://gitee.com/openharmony/docs"
            )
            print("     - Add to PATH environment variable")
        else:  # IOS
            print("     - macOS: brew install libimobiledevice")
            print("     - Linux: sudo apt-get install libimobiledevice-utils")
        all_passed = False
    else:
        # Double check by running version command
        try:
            if device_type == DeviceType.ADB:
                version_cmd = [tool_cmd, "version"]
            elif device_type == DeviceType.HDC:
                version_cmd = [tool_cmd, "-v"]
            else:  # IOS
                version_cmd = [tool_cmd, "-ln"]

            result = subprocess.run(
                version_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                print(f"✅ OK ({version_line if version_line else 'installed'})")
            else:
                print("❌ FAILED")
                print(f"   Error: {tool_name} command failed to run.")
                all_passed = False
        except FileNotFoundError:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command not found.")
            all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command timed out.")
            all_passed = False

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    print("2. Checking connected devices...", end=" ")
    try:
        if device_type == DeviceType.ADB:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            # Filter out header and empty lines, look for 'device' status
            devices = [
                line for line in lines[1:] if line.strip() and "\tdevice" in line
            ]
        elif device_type == DeviceType.HDC:
            result = subprocess.run(
                ["hdc", "list", "targets"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            devices = [line for line in lines if line.strip()]
        else:  # IOS
            ios_devices = list_ios_devices()
            devices = [d.device_id for d in ios_devices]

        if not devices:
            print("❌ FAILED")
            print("   Error: No devices connected.")
            print("   Solution:")
            if device_type == DeviceType.ADB:
                print("     1. Enable USB debugging on your Android device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --connect <ip>:<port>"
                )
            elif device_type == DeviceType.HDC:
                print("     1. Enable USB debugging on your HarmonyOS device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --device-type hdc --connect <ip>:<port>"
                )
            else:  # IOS
                print("     1. Connect your iOS device via USB")
                print("     2. Unlock device and tap 'Trust This Computer'")
                print("     3. Verify: idevice_id -l")
                print("     4. Or connect via WiFi using device IP")
            all_passed = False
        else:
            if device_type == DeviceType.ADB:
                device_ids = [d.split("\t")[0] for d in devices]
            elif device_type == DeviceType.HDC:
                device_ids = [d.strip() for d in devices]
            else:  # IOS
                device_ids = devices
            if device_id and device_id not in device_ids:
                print("❌ FAILED")
                print(f"   Error: Selected device '{device_id}' is not connected.")
                all_passed = False
            else:
                print(
                    f"✅ OK ({len(devices)} device(s): {', '.join(device_ids[:2])}{'...' if len(device_ids) > 2 else ''})"
                )
    except subprocess.TimeoutExpired:
        print("❌ FAILED")
        print(f"   Error: {tool_name} command timed out.")
        all_passed = False
    except Exception as e:
        print("❌ FAILED")
        print(f"   Error: {e}")
        all_passed = False

    # If no device connected, skip ADB Keyboard check
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 3: ADB Keyboard installed (only for ADB) or WebDriverAgent (for iOS)
    if device_type == DeviceType.ADB:
        print("3. Checking ADB Keyboard...", end=" ")
        try:
            result = subprocess.run(
                (["adb", "-s", device_id] if device_id else ["adb"])
                + ["shell", "ime", "list", "-a"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ime_list = result.stdout.strip()

            if "com.android.adbkeyboard/.AdbIME" in ime_list:
                print("✅ OK")
            else:
                print("❌ FAILED")
                print("   Error: ADB Keyboard is not installed on the device.")
                print("   Solution:")
                print("     1. Download ADB Keyboard APK from:")
                print(
                    "        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk"
                )
                print("     2. Install it on your device: adb install ADBKeyboard.apk")
                print(
                    "     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
                )
                all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print("   Error: ADB command timed out.")
            all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False
    elif device_type == DeviceType.HDC:
        # For HDC, skip keyboard check as it uses different input method
        print("3. Skipping keyboard check for HarmonyOS...", end=" ")
        print("✅ OK (using native input)")
    else:  # IOS
        # Check WebDriverAgent
        print(f"3. Checking WebDriverAgent ({wda_url})...", end=" ")
        try:
            conn = XCTestConnection(wda_url=wda_url)

            if conn.is_wda_ready():
                print("✅ OK")
                # Get WDA status for additional info
                status = conn.get_wda_status()
                if status:
                    session_id = status.get("sessionId", "N/A")
                    print(f"   Session ID: {session_id}")
            else:
                print("❌ FAILED")
                print("   Error: WebDriverAgent is not running or not accessible.")
                print("   Solution:")
                print("     1. Run WebDriverAgent on your iOS device via Xcode")
                print("     2. For USB: Set up port forwarding: iproxy 8100 8100")
                print(
                    "     3. For WiFi: Use device IP, e.g., --wda-url http://192.168.1.100:8100"
                )
                print("     4. Verify in browser: open http://localhost:8100/status")
                all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ All system checks passed!\n")
    else:
        print("❌ System check failed. Please fix the issues above.")

    return all_passed


def ensure_phone_control_ready(
    device_type: DeviceType,
    device_id: str | None = None,
    *,
    verbose: bool = True,
) -> bool:
    """Prepare the selected device for direct `phone` control."""
    if device_type != DeviceType.ADB:
        if verbose:
            if device_type == DeviceType.HDC:
                print(
                    "HarmonyOS input uses the native keyboard; no preparation needed."
                )
            else:
                print("iOS direct control is ready when WebDriverAgent is available.")
        return True

    from phone_agent.adb.input import ADB_KEYBOARD_IME, ensure_adb_keyboard_ready

    try:
        original_ime, changed = ensure_adb_keyboard_ready(device_id=device_id)
    except Exception as exc:
        if verbose:
            print(f"Error: {exc}")
            print(
                "Run `phone-use phone doctor` after installing and enabling ADB Keyboard "
                "to verify device prerequisites."
            )
        return False

    if verbose:
        if changed:
            previous = original_ime or "unknown"
            print(
                f"Prepared device input: switched from {previous} to {ADB_KEYBOARD_IME}"
            )
        else:
            print(f"Prepared device input: {ADB_KEYBOARD_IME} is already active")

    return True


def run_phone_doctor(
    device_type: DeviceType,
    device_id: str | None = None,
    wda_url: str = "http://localhost:8100",
) -> bool:
    """Check prerequisites for direct `phone` control."""
    ok = check_system_requirements(
        device_type=device_type,
        wda_url=wda_url,
        device_id=device_id,
    )
    if not ok:
        return False

    if device_type == DeviceType.ADB:
        print("4. Preparing ADB Keyboard for direct control...", end=" ")
        if ensure_phone_control_ready(device_type, device_id=device_id, verbose=False):
            print("✅ OK")
        else:
            print("❌ FAILED")
            print("   Error: Could not enable and switch to ADB Keyboard.")
            print(
                "   Solution: enable the keyboard on-device once, then run `phone-use phone prepare`."
            )
            print("-" * 50)
            print("❌ Phone doctor found issues. Please fix the items above.")
            return False

        print("-" * 50)
        print("✅ Phone doctor passed. Device is ready for direct control.\n")
    else:
        print("✅ Phone doctor passed. Device is ready for direct control.\n")

    return True


def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """
    Check if the model API is accessible and the specified model exists.

    Checks:
    1. Network connectivity to the API endpoint
    2. Model exists in the available models list

    Args:
        base_url: The API base URL
        model_name: The model name to check
        api_key: The API key for authentication

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking model API...")
    print("-" * 50)

    all_passed = True

    # Check 1: Network connectivity using chat API
    print(f"1. Checking API connectivity ({base_url})...", end=" ")
    try:
        # Create OpenAI client
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)

        # Use chat completion to test connectivity (more universally supported than /models)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=1.0,
            stream=False,
        )

        # Check if we got a valid response
        if response.choices and len(response.choices) > 0:
            print("✅ OK")
        else:
            print("❌ FAILED")
            print("   Error: Received empty response from API")
            all_passed = False

    except Exception as e:
        print("❌ FAILED")
        error_msg = str(e)

        # Provide more specific error messages
        if "Connection refused" in error_msg or "Connection error" in error_msg:
            print(f"   Error: Cannot connect to {base_url}")
            print("   Solution:")
            print("     1. Check if the model server is running")
            print("     2. Verify the base URL is correct")
            print(f"     3. Try: curl {base_url}/chat/completions")
        elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            print(f"   Error: Connection to {base_url} timed out")
            print("   Solution:")
            print("     1. Check your network connection")
            print("     2. Verify the server is responding")
        elif (
            "Name or service not known" in error_msg
            or "nodename nor servname" in error_msg
        ):
            print("   Error: Cannot resolve hostname")
            print("   Solution:")
            print("     1. Check the URL is correct")
            print("     2. Verify DNS settings")
        else:
            print(f"   Error: {error_msg}")

        all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ Model API checks passed!\n")
    else:
        print("❌ Model API check failed. Please fix the issues above.")

    return all_passed


def _add_common_device_args(parser: argparse.ArgumentParser) -> None:
    """Add device selection arguments shared across agent mode and phone subcommands."""
    parser.add_argument(
        "--device-type",
        type=str,
        choices=["adb", "hdc", "ios"],
        default=os.getenv("PHONE_AGENT_DEVICE_TYPE", "adb"),
        help="Device type: adb for Android, hdc for HarmonyOS, ios for iPhone (default: adb)",
    )
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="Device ID (ADB serial / HDC target / iOS UDID)",
    )
    parser.add_argument(
        "--wda-url",
        type=str,
        default=os.getenv("PHONE_AGENT_WDA_URL", "http://localhost:8100"),
        help="WebDriverAgent URL for iOS (default: http://localhost:8100)",
    )


def _is_phone_mode(argv: list[str]) -> bool:
    """
    Return True when the user invoked phone-control mode.

    We look for the literal token 'phone' as the first non-flag positional
    argument.  Flags start with '-'; their values are skipped.
    """
    skip_next = False
    # Options that consume a following value token
    value_flags = {
        "--device-type",
        "--device-id",
        "-d",
        "--wda-url",
        "--base-url",
        "--model",
        "--apikey",
        "--max-steps",
        "--connect",
        "-c",
        "--disconnect",
        "--enable-tcpip",
        "--lang",
    }
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token in value_flags:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        # First bare positional
        return token == "phone"
    return False


def _normalize_phone_argv(argv: list[str]) -> list[str]:
    """Move shared phone-mode device flags ahead of the action parser.

    This lets users place `--device-id`, `--device-type`, and `--wda-url`
    either before `phone`, immediately after it, or after the specific phone
    action and its arguments.
    """

    normalized: list[str] = []
    deferred: list[str] = []
    i = 0

    while i < len(argv):
        token = argv[i]

        if token in {"--device-type", "--device-id", "-d", "--wda-url"}:
            deferred.append(token)
            if i + 1 < len(argv):
                deferred.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue

        if any(
            token.startswith(prefix)
            for prefix in ("--device-type=", "--device-id=", "--wda-url=")
        ):
            deferred.append(token)
            i += 1
            continue

        normalized.append(token)
        i += 1

    return deferred + normalized


def _build_agent_parser() -> argparse.ArgumentParser:
    """Return an ArgumentParser for agent mode (existing behaviour)."""
    parser = argparse.ArgumentParser(
        description="Phone Agent - AI-powered phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Agent mode — AI operates the device autonomously.

Examples:
    phone-use
    phone-use --base-url http://localhost:8000/v1
    phone-use --apikey sk-xxxxx
    phone-use --device-id emulator-5554
    phone-use --connect 192.168.1.100:5555
    phone-use --list-devices
    phone-use --enable-tcpip
    phone-use --device-type ios "Open Safari and search for iPhone tips"
    phone-use --device-type ios --wda-url http://192.168.1.100:8100
    phone-use --device-type ios --list-devices
    phone-use --device-type ios --wda-status
    phone-use --device-type ios --pair

Direct device control (no AI) — use the 'phone' subcommand:
    phone-use phone --help
        """,
    )
    _add_common_device_args(parser)
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
        help="Model API base URL",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b"),
        help="Model name",
    )
    parser.add_argument(
        "--apikey",
        type=str,
        default=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
        help="API key for model authentication",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_STEPS", "100")),
        help="Maximum steps per task",
    )
    parser.add_argument(
        "--connect",
        "-c",
        type=str,
        metavar="ADDRESS",
        help="Connect to remote device (e.g., 192.168.1.100:5555)",
    )
    parser.add_argument(
        "--disconnect",
        type=str,
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device (or 'all' to disconnect all)",
    )
    parser.add_argument(
        "--list-devices", action="store_true", help="List connected devices and exit"
    )
    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
        help="Enable TCP/IP debugging on USB device (default port: 5555)",
    )
    parser.add_argument(
        "--pair",
        action="store_true",
        help="Pair with iOS device (required for some operations)",
    )
    parser.add_argument(
        "--wda-status",
        action="store_true",
        help="Show WebDriverAgent status and exit (iOS only)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )
    parser.add_argument(
        "--lang",
        type=str,
        choices=["cn", "en"],
        default=os.getenv("PHONE_AGENT_LANG", "cn"),
        help="Language for system prompt (cn or en, default: cn)",
    )
    parser.add_argument(
        "task",
        nargs="?",
        type=str,
        help="Task to execute (interactive mode if not provided)",
    )
    return parser


def _build_phone_parser() -> argparse.ArgumentParser:
    """Return an ArgumentParser for phone-control mode."""
    # Use the actual invocation name so `phone-use phone --help` shows
    # "phone-use phone" rather than the hard-coded "main.py phone".
    prog_name = os.path.basename(sys.argv[0])
    parser = argparse.ArgumentParser(
        prog=f"{prog_name} phone",
        description="Directly operate the connected phone without running the AI agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    phone-use phone tap 540 960
    phone-use phone double-tap 540 960
    phone-use phone long-press 540 960 --duration-ms 2000
    phone-use phone swipe 540 1200 540 400 --duration-ms 400
    phone-use phone prepare
    phone-use phone doctor
    phone-use phone type "Hello world"
    phone-use phone clear
    phone-use phone back
    phone-use phone home
    phone-use phone launch WeChat
    phone-use phone screenshot --output screen.png
    phone-use phone state --output state.json
    phone-use phone current-app
    phone-use --device-type hdc phone tap 500 1000
    phone-use --device-type ios phone tap 200 400
        """,
    )
    # Device flags may appear either before or after 'phone' on the command
    # line.  We parse the full argv (minus 'phone') so both positions work.
    _add_common_device_args(parser)

    action_parsers = parser.add_subparsers(dest="phone_action", metavar="ACTION")
    action_parsers.required = True

    # --- tap ---
    p = action_parsers.add_parser("tap", help="Tap at pixel coordinates")
    p.add_argument("x", type=int, help="X coordinate in pixels")
    p.add_argument("y", type=int, help="Y coordinate in pixels")
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Post-action delay in seconds (default: device timing config)",
    )

    # --- double-tap ---
    p = action_parsers.add_parser("double-tap", help="Double-tap at pixel coordinates")
    p.add_argument("x", type=int, help="X coordinate in pixels")
    p.add_argument("y", type=int, help="Y coordinate in pixels")
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Post-action delay in seconds",
    )

    # --- long-press ---
    p = action_parsers.add_parser("long-press", help="Long-press at pixel coordinates")
    p.add_argument("x", type=int, help="X coordinate in pixels")
    p.add_argument("y", type=int, help="Y coordinate in pixels")
    p.add_argument(
        "--duration-ms",
        type=int,
        default=3000,
        metavar="MS",
        help="Press duration in milliseconds (default: 3000)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Post-action delay in seconds",
    )

    # --- swipe ---
    p = action_parsers.add_parser("swipe", help="Swipe between two pixel coordinates")
    p.add_argument("start_x", type=int, help="Start X coordinate in pixels")
    p.add_argument("start_y", type=int, help="Start Y coordinate in pixels")
    p.add_argument("end_x", type=int, help="End X coordinate in pixels")
    p.add_argument("end_y", type=int, help="End Y coordinate in pixels")
    p.add_argument(
        "--duration-ms",
        type=int,
        default=None,
        metavar="MS",
        help="Swipe duration in milliseconds",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Post-action delay in seconds",
    )

    # --- type ---
    p = action_parsers.add_parser("type", help="Type text into the focused field")
    p.add_argument("text", type=str, help="Text to type")

    # --- prepare ---
    action_parsers.add_parser(
        "prepare",
        help="Prepare the device for direct control (e.g. activate ADB Keyboard)",
    )

    # --- doctor ---
    action_parsers.add_parser(
        "doctor",
        help="Check direct-control prerequisites and report problems",
    )

    # --- clear ---
    action_parsers.add_parser("clear", help="Clear text in the focused field")

    # --- back ---
    p = action_parsers.add_parser("back", help="Press the back button")
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Post-action delay in seconds",
    )

    # --- home ---
    p = action_parsers.add_parser("home", help="Go to the home screen")
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Post-action delay in seconds",
    )

    # --- launch ---
    p = action_parsers.add_parser("launch", help="Launch an app by name")
    p.add_argument(
        "app_name", type=str, help="App name (e.g. WeChat, Safari, Settings)"
    )
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Post-action delay in seconds",
    )

    # --- screenshot ---
    p = action_parsers.add_parser(
        "screenshot", help="Capture a screenshot and save to file"
    )
    p.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        metavar="PATH",
        help="Output file path (e.g. screen.png)",
    )

    # --- current-app ---
    action_parsers.add_parser("current-app", help="Print the currently active app")

    # --- list-apps ---
    action_parsers.add_parser(
        "list-apps", help="List installed apps on the connected device"
    )

    # --- state ---
    p = action_parsers.add_parser(
        "state", help="Dump the current phone state with native UI coordinates"
    )
    p.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        metavar="PATH",
        help="Optional output file path for the full state JSON",
    )

    return parser


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Routes to the agent-mode parser or the phone-control parser depending on
    whether 'phone' appears as the first non-flag positional token in sys.argv.
    """
    raw_argv = sys.argv[1:]

    if _is_phone_mode(raw_argv):
        # Strip the literal 'phone' token and parse the remainder with the
        # phone parser, keeping any global flags (--device-type etc.) that
        # appeared before 'phone'.
        phone_idx = next(i for i, t in enumerate(raw_argv) if t == "phone")
        # Flags before 'phone' + everything after 'phone'
        phone_argv = _normalize_phone_argv(
            raw_argv[:phone_idx] + raw_argv[phone_idx + 1 :]
        )
        parser = _build_phone_parser()
        args = parser.parse_args(phone_argv)
        args.command = "phone"
        return args
    else:
        parser = _build_agent_parser()
        args = parser.parse_args(raw_argv)
        args.command = None
        return args


def handle_ios_device_commands(args) -> bool:
    """
    Handle iOS device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    conn = XCTestConnection(wda_url=args.wda_url)

    # Handle --list-devices
    if args.list_devices:
        devices = list_ios_devices()
        if not devices:
            print("No iOS devices connected.")
            print("\nTroubleshooting:")
            print("  1. Connect device via USB")
            print("  2. Unlock device and trust this computer")
            print("  3. Run: idevice_id -l")
        else:
            print("Connected iOS devices:")
            print("-" * 70)
            for device in devices:
                conn_type = device.connection_type.value
                model_info = f"{device.model}" if device.model else "Unknown"
                ios_info = f"iOS {device.ios_version}" if device.ios_version else ""
                name_info = device.device_name or "Unnamed"

                print(f"  ✓ {name_info}")
                print(f"    UUID: {device.device_id}")
                print(f"    Model: {model_info}")
                print(f"    OS: {ios_info}")
                print(f"    Connection: {conn_type}")
                print("-" * 70)
        return True

    # Handle --pair
    if args.pair:
        print("Pairing with iOS device...")
        success, message = conn.pair_device(args.device_id)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --wda-status
    if args.wda_status:
        print(f"Checking WebDriverAgent status at {args.wda_url}...")
        print("-" * 50)

        if conn.is_wda_ready():
            print("✓ WebDriverAgent is running")

            status = conn.get_wda_status()
            if status:
                print("\nStatus details:")
                value = status.get("value", {})
                print(f"  Session ID: {status.get('sessionId', 'N/A')}")
                print(f"  Build: {value.get('build', {}).get('time', 'N/A')}")

                current_app = value.get("currentApp", {})
                if current_app:
                    print("\nCurrent App:")
                    print(f"  Bundle ID: {current_app.get('bundleId', 'N/A')}")
                    print(f"  Process ID: {current_app.get('pid', 'N/A')}")
        else:
            print("✗ WebDriverAgent is not running")
            print("\nPlease start WebDriverAgent on your iOS device:")
            print("  1. Open WebDriverAgent.xcodeproj in Xcode")
            print("  2. Select your device")
            print("  3. Run WebDriverAgentRunner (Product > Test or Cmd+U)")
            print("  4. For USB: Run port forwarding: iproxy 8100 8100")

        return True

    return False


def handle_device_commands(args) -> bool:
    """
    Handle device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    device_type = (
        DeviceType.ADB
        if args.device_type == "adb"
        else (DeviceType.HDC if args.device_type == "hdc" else DeviceType.IOS)
    )

    # Handle iOS-specific commands
    if device_type == DeviceType.IOS:
        return handle_ios_device_commands(args)

    device_factory = get_device_factory()
    ConnectionClass = device_factory.get_connection_class()
    conn = ConnectionClass()

    # Handle --list-devices
    if args.list_devices:
        devices = device_factory.list_devices()
        if not devices:
            print("No devices connected.")
        else:
            print("Connected devices:")
            print("-" * 60)
            for device in devices:
                status_icon = "✓" if device.status == "device" else "✗"
                conn_type = device.connection_type.value
                model_info = f" ({device.model})" if device.model else ""
                print(
                    f"  {status_icon} {device.device_id:<30} [{conn_type}]{model_info}"
                )
        return True

    # Handle --connect
    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'✓' if success else '✗'} {message}")
        if success:
            # Set as default device
            args.device_id = args.connect
        return not success  # Continue if connection succeeded

    # Handle --disconnect
    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --enable-tcpip
    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'✓' if success else '✗'} {message}")

        if success:
            # Try to get device IP
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print("\nYou can now connect remotely using:")
                print(f"  python main.py --connect {ip}:{port}")
                print("\nOr via ADB directly:")
                print(f"  adb connect {ip}:{port}")
            else:
                print("\nCould not determine device IP. Check device WiFi settings.")
        return True

    return False


def run_direct_phone(args: argparse.Namespace) -> None:
    """
    Execute a direct phone control command without running the AI agent.

    Dispatches to the appropriate device backend (ADB / HDC / iOS) based on
    --device-type, then calls the requested action and prints the result.
    """
    # Resolve device type from whichever parser captured it (parent or phone sub-parser).
    device_type_str: str = getattr(args, "device_type", "adb")
    device_id: str | None = getattr(args, "device_id", None)
    wda_url: str = getattr(args, "wda_url", "http://localhost:8100")

    if device_type_str == "adb":
        device_type = DeviceType.ADB
    elif device_type_str == "hdc":
        device_type = DeviceType.HDC
    else:
        device_type = DeviceType.IOS

    # --- resolve action name (may be None if user typed just 'phone') ---
    action: str | None = getattr(args, "phone_action", None)
    if not action:
        # Print usage hint and exit
        print("Usage: python main.py phone <action> [options]")
        print("Run 'python main.py phone --help' for available actions.")
        sys.exit(1)

    action_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": "phone",
        "action": action,
        "device_type": device_type.value,
        "device_id": device_id,
        "cwd": os.getcwd(),
        "argv": sys.argv,
        "status": "started",
    }

    if action == "doctor":
        if not run_phone_doctor(device_type, device_id=device_id, wda_url=wda_url):
            sys.exit(1)
        return

    if action == "prepare":
        if device_type in {DeviceType.HDC, DeviceType.IOS}:
            if not check_system_requirements(
                device_type=device_type,
                wda_url=wda_url,
                device_id=device_id,
            ):
                sys.exit(1)
            if device_type == DeviceType.HDC:
                print("HarmonyOS device is ready for direct control.")
            else:
                print(
                    "WebDriverAgent is reachable. iOS device is ready for direct control."
                )
            return

        if not ensure_phone_control_ready(
            device_type, device_id=device_id, verbose=True
        ):
            sys.exit(1)
        return

    def _capture_phone_state(get_current_app, get_screenshot) -> dict:
        snapshot = {}
        try:
            snapshot["current_app"] = get_current_app()
        except Exception as exc:
            snapshot["current_app_error"] = str(exc)

        try:
            shot = get_screenshot()
            snapshot["screen_width"] = shot.width
            snapshot["screen_height"] = shot.height
            snapshot["screenshot_sha256"] = hash_screenshot_base64(shot.base64_data)
        except Exception as exc:
            snapshot["screenshot_error"] = str(exc)

        return snapshot

    def _log_phone_action(**fields) -> str:
        action_log.update(fields)
        return str(append_phone_action_log(action_log))

    def _record_no_change_note(log_path: str) -> None:
        state_change = action_log.get("state_change", {})
        if state_change.get("likely_no_visible_change"):
            print(
                "Note: command completed, but the current app and screenshot did not change. "
                f"Check the log for details: {log_path}"
            )

    def _print_labeled_apps(
        identifiers: list[str], lookup_label, heading: str, note: str | None = None
    ) -> None:
        print(heading)
        for identifier in identifiers:
            label = lookup_label(identifier)
            if label:
                print(f"  - {label} ({identifier})")
            else:
                print(f"  - {identifier}")
        if note:
            print(f"\nNote: {note}")

    def _run_tool_capture(cmd: list[str], timeout: int = 5) -> str | None:
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

        if result.returncode != 0:
            return None

        return result.stdout.strip() or None

    def _parse_prefixed_value(output: str | None, prefix: str) -> str | None:
        if not output:
            return None

        for line in output.splitlines():
            line = line.strip()
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()

        return None

    def _get_android_device_info() -> dict[str, str]:
        cmd = ["adb"]
        if device_id:
            cmd.extend(["-s", device_id])

        info: dict[str, str] = {}

        model = _run_tool_capture(cmd + ["shell", "getprop", "ro.product.model"])
        manufacturer = _run_tool_capture(
            cmd + ["shell", "getprop", "ro.product.manufacturer"]
        )
        android_version = _run_tool_capture(
            cmd + ["shell", "getprop", "ro.build.version.release"]
        )
        physical_size = _parse_prefixed_value(
            _run_tool_capture(cmd + ["shell", "wm", "size"]), "Physical size"
        )
        density = _parse_prefixed_value(
            _run_tool_capture(cmd + ["shell", "wm", "density"]), "Physical density"
        )

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

    def _get_ios_device_info(
        shot_width: int | None = None, shot_height: int | None = None
    ) -> dict[str, str]:
        from phone_agent.xctest.device import get_screen_size

        info: dict[str, str] = {}
        device_info = conn.get_device_info(device_id=device_id)

        if device_info:
            if device_info.device_name:
                info["Device"] = device_info.device_name
            if device_info.model:
                info["Model"] = device_info.model
            if device_info.ios_version:
                info["iOS version"] = device_info.ios_version

        if shot_width and shot_height:
            info["Physical size"] = f"{shot_width}x{shot_height}"

        try:
            logical_width, logical_height = get_screen_size(
                wda_url=wda_url, session_id=session_id
            )
        except Exception:
            logical_width = logical_height = None

        if logical_width and logical_height:
            info["Logical size"] = f"{logical_width}x{logical_height}"

        return info

    # ------------------------------------------------------------------ #
    # iOS — delegate everything through xctest module + WDA session       #
    # ------------------------------------------------------------------ #
    if device_type == DeviceType.IOS:
        import phone_agent.xctest as xctest
        from phone_agent.xctest import XCTestConnection

        conn = XCTestConnection(wda_url=wda_url)
        if not conn.is_wda_ready(timeout=5):
            print(f"Error: WebDriverAgent is not reachable at {wda_url}")
            print("Make sure WDA is running and port forwarding is set up.")
            sys.exit(1)

        ok, session_id = conn.start_wda_session()
        if not ok or not session_id:
            print("Error: Failed to create a WDA session.")
            sys.exit(1)

        action_log["wda_url"] = wda_url
        action_log["wda_session_id"] = session_id

        before_state = None
        if action in MUTATING_PHONE_ACTIONS:
            before_state = _capture_phone_state(
                lambda: xctest.get_current_app(wda_url=wda_url, session_id=session_id),
                lambda: xctest.get_screenshot(
                    wda_url=wda_url,
                    session_id=session_id,
                    device_id=device_id,
                ),
            )
            action_log["before"] = before_state

        try:
            if action == "tap":
                xctest.tap(
                    args.x,
                    args.y,
                    wda_url=wda_url,
                    session_id=session_id,
                    delay=args.delay if args.delay is not None else 1.0,
                )
                print(f"Tapped ({args.x}, {args.y})")
                action_log["params"] = {"x": args.x, "y": args.y, "delay": args.delay}

            elif action == "double-tap":
                xctest.double_tap(
                    args.x,
                    args.y,
                    wda_url=wda_url,
                    session_id=session_id,
                    delay=args.delay if args.delay is not None else 1.0,
                )
                print(f"Double-tapped ({args.x}, {args.y})")
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
                print(f"Long-pressed ({args.x}, {args.y}) for {args.duration_ms} ms")
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
                print(
                    f"Swiped ({args.start_x}, {args.start_y}) -> ({args.end_x}, {args.end_y})"
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
                print(f"Typed: {args.text!r}")
                action_log["params"] = {"text": args.text}

            elif action == "clear":
                from phone_agent.xctest.input import clear_text as xctest_clear

                xctest_clear(wda_url=wda_url, session_id=session_id)
                print("Cleared text")
                action_log["params"] = {}

            elif action == "back":
                xctest.back(
                    wda_url=wda_url,
                    session_id=session_id,
                    delay=args.delay if args.delay is not None else 1.0,
                )
                print("Pressed back")
                action_log["params"] = {"delay": args.delay}

            elif action == "home":
                xctest.home(
                    wda_url=wda_url,
                    session_id=session_id,
                    delay=args.delay if args.delay is not None else 1.0,
                )
                print("Went to home screen")
                action_log["params"] = {"delay": args.delay}

            elif action == "launch":
                success = xctest.launch_app(
                    args.app_name,
                    wda_url=wda_url,
                    session_id=session_id,
                    delay=args.delay if args.delay is not None else 1.0,
                )
                if success:
                    print(f"Launched: {args.app_name}")
                    action_log["params"] = {
                        "app_name": args.app_name,
                        "delay": args.delay,
                    }
                else:
                    raise ValueError(
                        f"Could not launch app '{args.app_name}'. "
                        "Run 'python main.py --device-type ios phone list-apps' to inspect installed apps, or pass a known label from the app map."
                    )

            elif action == "screenshot":
                from phone_agent.xctest.screenshot import (
                    get_screenshot as xctest_screenshot,
                )

                shot = xctest_screenshot(
                    wda_url=wda_url, session_id=session_id, device_id=device_id
                )
                png_bytes = base64.b64decode(shot.base64_data)
                with open(args.output, "wb") as f:
                    f.write(png_bytes)
                print(
                    f"Screenshot saved to: {args.output} ({shot.width}x{shot.height})"
                )
                action_log["params"] = {"output": args.output}
                action_log["result"] = {
                    "output": os.path.abspath(args.output),
                    "width": shot.width,
                    "height": shot.height,
                    "screenshot_sha256": hash_screenshot_base64(shot.base64_data),
                }

            elif action == "current-app":
                app = xctest.get_current_app(wda_url=wda_url, session_id=session_id)
                print(f"Current app: {app}")
                action_log["result"] = {"current_app": app}

            elif action == "list-apps":
                bundle_ids = xctest.list_installed_apps(device_id=device_id)
                _print_labeled_apps(
                    bundle_ids,
                    get_ios_app_name,
                    "Installed iOS apps:",
                    "labels from `phone_agent/config/apps_ios.py` are shown when known; otherwise the bundle id is printed.",
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
                state["device_info"] = _get_ios_device_info(shot.width, shot.height)
                _print_or_save_state(state, args.output)
                action_log["params"] = {"output": args.output}
                action_log["result"] = {
                    "device_info": state.get("device_info"),
                    "node_count": state.get("node_count"),
                    "output": os.path.abspath(args.output) if args.output else None,
                }

            if action in MUTATING_PHONE_ACTIONS:
                after_state = _capture_phone_state(
                    lambda: xctest.get_current_app(
                        wda_url=wda_url, session_id=session_id
                    ),
                    lambda: xctest.get_screenshot(
                        wda_url=wda_url,
                        session_id=session_id,
                        device_id=device_id,
                    ),
                )
                action_log["after"] = after_state
                action_log["state_change"] = assess_state_change(
                    before_state, after_state
                )

            log_path = _log_phone_action(status="success")
            _record_no_change_note(log_path)

        except Exception as e:
            log_path = _log_phone_action(status="error", error=str(e))
            print(f"Error: {e}")
            print(f"Action log written to: {log_path}")
            sys.exit(1)
        return

    # ------------------------------------------------------------------ #
    # Android (ADB) / HarmonyOS (HDC) — use DeviceFactory                #
    # ------------------------------------------------------------------ #
    set_device_type(device_type)

    if device_type == DeviceType.HDC:
        from phone_agent.hdc import set_hdc_verbose

        set_hdc_verbose(False)  # keep phone commands clean; user can set env var
        if action == "state":
            print("Error: state is currently supported on adb and ios, not hdc.")
            sys.exit(1)

    factory = get_device_factory()

    if device_type == DeviceType.ADB and not ensure_phone_control_ready(
        device_type,
        device_id=device_id,
        verbose=False,
    ):
        sys.exit(1)

    before_state = None
    if action in MUTATING_PHONE_ACTIONS:
        before_state = _capture_phone_state(
            lambda: factory.get_current_app(device_id=device_id),
            lambda: factory.get_screenshot(device_id=device_id),
        )
        action_log["before"] = before_state

    try:
        if action == "tap":
            factory.tap(args.x, args.y, device_id=device_id, delay=args.delay)
            print(f"Tapped ({args.x}, {args.y})")
            action_log["params"] = {"x": args.x, "y": args.y, "delay": args.delay}

        elif action == "double-tap":
            factory.double_tap(args.x, args.y, device_id=device_id, delay=args.delay)
            print(f"Double-tapped ({args.x}, {args.y})")
            action_log["params"] = {"x": args.x, "y": args.y, "delay": args.delay}

        elif action == "long-press":
            factory.long_press(
                args.x,
                args.y,
                duration_ms=args.duration_ms,
                device_id=device_id,
                delay=args.delay,
            )
            print(f"Long-pressed ({args.x}, {args.y}) for {args.duration_ms} ms")
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
            print(
                f"Swiped ({args.start_x}, {args.start_y}) -> ({args.end_x}, {args.end_y})"
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
            print(f"Typed: {args.text!r}")
            action_log["params"] = {"text": args.text}

        elif action == "clear":
            factory.clear_text(device_id=device_id)
            print("Cleared text")
            action_log["params"] = {}

        elif action == "back":
            factory.back(device_id=device_id, delay=args.delay)
            print("Pressed back")
            action_log["params"] = {"delay": args.delay}

        elif action == "home":
            factory.home(device_id=device_id, delay=args.delay)
            print("Went to home screen")
            action_log["params"] = {"delay": args.delay}

        elif action == "launch":
            success = factory.launch_app(
                args.app_name, device_id=device_id, delay=args.delay
            )
            if success:
                print(f"Launched: {args.app_name}")
                action_log["params"] = {
                    "app_name": args.app_name,
                    "delay": args.delay,
                }
            else:
                dt = args.device_type
                raise ValueError(
                    f"Could not launch app '{args.app_name}'. "
                    f"Run 'python main.py --device-type {dt} phone list-apps' to inspect installed apps, or pass a known label from the app map."
                )

        elif action == "screenshot":
            shot = factory.get_screenshot(device_id=device_id)
            png_bytes = base64.b64decode(shot.base64_data)
            with open(args.output, "wb") as f:
                f.write(png_bytes)
            print(f"Screenshot saved to: {args.output} ({shot.width}x{shot.height})")
            action_log["params"] = {"output": args.output}
            action_log["result"] = {
                "output": os.path.abspath(args.output),
                "width": shot.width,
                "height": shot.height,
                "screenshot_sha256": hash_screenshot_base64(shot.base64_data),
            }

        elif action == "current-app":
            app = factory.get_current_app(device_id=device_id)
            print(f"Current app: {app}")
            action_log["result"] = {"current_app": app}

        elif action == "list-apps":
            packages = factory.list_installed_apps(device_id=device_id)
            if device_type == DeviceType.HDC:
                _print_labeled_apps(
                    packages,
                    get_harmony_app_name,
                    "Installed HarmonyOS apps:",
                    "labels from `phone_agent/config/apps_harmonyos.py` are shown when known; otherwise the bundle name is printed.",
                )
            else:
                _print_labeled_apps(
                    packages,
                    get_android_app_name,
                    "Installed Android apps:",
                    "labels from `phone_agent/config/apps.py` are shown when known; otherwise the package name is printed.",
                )
            action_log["result"] = {"installed_app_count": len(packages)}

        elif action == "state":
            shot = factory.get_screenshot(device_id=device_id)
            state = factory.get_ui_tree(
                device_id=device_id,
                screen_width=shot.width,
                screen_height=shot.height,
            )
            if device_type == DeviceType.ADB:
                state["device_info"] = _get_android_device_info()
            _print_or_save_state(state, args.output)
            action_log["params"] = {"output": args.output}
            action_log["result"] = {
                "device_info": state.get("device_info"),
                "node_count": state.get("node_count"),
                "output": os.path.abspath(args.output) if args.output else None,
            }

        if action in MUTATING_PHONE_ACTIONS:
            after_state = _capture_phone_state(
                lambda: factory.get_current_app(device_id=device_id),
                lambda: factory.get_screenshot(device_id=device_id),
            )
            action_log["after"] = after_state
            action_log["state_change"] = assess_state_change(before_state, after_state)

        log_path = _log_phone_action(status="success")
        _record_no_change_note(log_path)

    except Exception as e:
        log_path = _log_phone_action(status="error", error=str(e))
        print(f"Error: {e}")
        print(f"Action log written to: {log_path}")
        sys.exit(1)


def _print_or_save_state(state: dict, output_path: str | None) -> None:
    """Print the summarized phone state and optionally save the full payload."""
    summarized_state = summarize_ui_tree_for_model(state)
    device_info = summarized_state.pop("device_info", None)
    payload = json.dumps(summarized_state, ensure_ascii=False, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(state, ensure_ascii=False, indent=2))
            file_obj.write("\n")
        print(f"Full state saved to: {output_path}")

    if isinstance(device_info, dict) and device_info:
        print("Device info:")
        for label, value in device_info.items():
            print(f"{label}: {value}")
        print()

    print(payload)


def main():
    """Main entry point."""
    args = parse_args()

    # ------------------------------------------------------------------ #
    # Phone mode — direct device control, no AI agent                    #
    # ------------------------------------------------------------------ #
    if getattr(args, "command", None) == "phone":
        run_direct_phone(args)
        return

    # Set device type globally based on args
    if args.device_type == "adb":
        device_type = DeviceType.ADB
    elif args.device_type == "hdc":
        device_type = DeviceType.HDC
    else:  # ios
        device_type = DeviceType.IOS

    # Set device type globally for non-iOS devices
    if device_type != DeviceType.IOS:
        set_device_type(device_type)

    # Enable HDC verbose mode if using HDC
    if device_type == DeviceType.HDC:
        from phone_agent.hdc import set_hdc_verbose

        set_hdc_verbose(True)

    # Handle device commands (these may need partial system checks)
    if handle_device_commands(args):
        return

    # Run system requirements check before proceeding
    if not check_system_requirements(
        device_type,
        wda_url=args.wda_url
        if device_type == DeviceType.IOS
        else "http://localhost:8100",
        device_id=args.device_id,
    ):
        sys.exit(1)

    # Check model API connectivity and model availability
    if not check_model_api(args.base_url, args.model, args.apikey):
        sys.exit(1)

    # Create configurations and agent based on device type
    model_config = ModelConfig(
        base_url=args.base_url,
        model_name=args.model,
        api_key=args.apikey,
        lang=args.lang,
    )

    if device_type == DeviceType.IOS:
        # Create iOS agent
        agent_config = IOSAgentConfig(
            max_steps=args.max_steps,
            wda_url=args.wda_url,
            device_id=args.device_id,
            verbose=not args.quiet,
            lang=args.lang,
        )

        agent = IOSPhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )
    else:
        # Create Android/HarmonyOS agent
        agent_config = AgentConfig(
            max_steps=args.max_steps,
            device_id=args.device_id,
            verbose=not args.quiet,
            lang=args.lang,
        )

        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )

    # Print header
    print("=" * 50)
    if device_type == DeviceType.IOS:
        print("Phone Agent iOS - AI-powered iOS automation")
    else:
        print("Phone Agent - AI-powered phone automation")
    print("=" * 50)
    print(f"Model: {model_config.model_name}")
    print(f"Base URL: {model_config.base_url}")
    print(f"Max Steps: {agent_config.max_steps}")
    print(f"Language: {agent_config.lang}")
    print(f"Device Type: {args.device_type.upper()}")

    # Show iOS-specific config
    if device_type == DeviceType.IOS:
        print(f"WDA URL: {args.wda_url}")

    # Show device info
    if device_type == DeviceType.IOS:
        devices = list_ios_devices()
        if agent_config.device_id:
            print(f"Device: {agent_config.device_id}")
        elif devices:
            device = devices[0]
            print(f"Device: {device.device_name or device.device_id[:16]}")
            if device.model and device.ios_version:
                print(f"        {device.model}, iOS {device.ios_version}")
    else:
        device_factory = get_device_factory()
        devices = device_factory.list_devices()
        if agent_config.device_id:
            print(f"Device: {agent_config.device_id}")
        elif devices:
            print(f"Device: {devices[0].device_id} (auto-detected)")

    print("=" * 50)

    # Run with provided task or enter interactive mode
    if args.task:
        print(f"\nTask: {args.task}\n")
        result = agent.run(args.task)
        print(f"\nResult: {result}")
    else:
        # Interactive mode
        print("\nEntering interactive mode. Type 'quit' to exit.\n")

        while True:
            try:
                task = input("Enter your task: ").strip()

                if task.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                if not task:
                    continue

                print()
                result = agent.run(task)
                print(f"\nResult: {result}\n")
                agent.reset()

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
