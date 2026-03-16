# Phone CLI — Direct Device Control

The `phone` subcommand lets you operate a connected device directly from the command line — no AI model, no agent loop. Each action maps 1-to-1 to a device operation.

```
phone-use [DEVICE FLAGS] phone <action> [ACTION FLAGS]
```

---

## Table of Contents

- [One-Time Setup](#one-time-setup)
- [Setup](#setup)
- [Device Flags](#device-flags)
- [Actions](#actions)
  - [tap](#tap)
  - [double-tap](#double-tap)
  - [long-press](#long-press)
  - [swipe](#swipe)
  - [type](#type)
  - [clear](#clear)
  - [back](#back)
  - [home](#home)
  - [launch](#launch)
  - [screenshot](#screenshot)
  - [current-app](#current-app)
- [Coordinate System](#coordinate-system)
- [Best Practices](#best-practices)

---

## One-Time Setup

Install the executable once from the repository root:

```bash
./install.sh
```

This performs a global install by default:

- with `uv`: installs `phone-use` as a global tool
- with `pip`: installs `phone-use` with `--user`
- expected command location: `~/.local/bin/phone-use`

If you want dev tools too:

```bash
./install.sh --dev
```

If you prefer installation into the current environment instead of a global tool:

```bash
./install.sh --local
```

After installation, the main command is:

```bash
phone-use --help
phone-use phone --help
```

If `phone-use` is not found after a global install, add this to your shell config:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then restart the shell or run:

```bash
source ~/.zshrc
```

Use `./install.sh --local` only if you explicitly want the command tied to the current environment.

## Setup

The same device requirements apply whether you use agent mode or phone mode.

| Device | Requirement |
|---|---|
| Android (ADB) | `adb` installed, USB debugging enabled, ADB Keyboard APK installed |
| HarmonyOS (HDC) | `hdc` installed, USB debugging enabled |
| iOS | `libimobiledevice` installed, WebDriverAgent running, port forwarding active |

Verify your setup:
```bash
phone-use --list-devices
phone-use --device-type ios --wda-status
```

---

## Device Flags

These flags go **before** `phone` on the command line and apply to every action.

| Flag | Default | Description |
|---|---|---|
| `--device-type adb\|hdc\|ios` | `adb` | Which device backend to use |
| `--device-id <id>` | auto-detect | ADB serial, HDC target, or iOS UDID |
| `--wda-url <url>` | `http://localhost:8100` | WebDriverAgent base URL (iOS only) |

```bash
# Android (default)
phone-use phone tap 540 960

# HarmonyOS
phone-use --device-type hdc phone tap 540 960

# iOS
phone-use --device-type ios phone tap 540 960

# Specific device
phone-use --device-id emulator-5554 phone tap 540 960

# iOS over WiFi
phone-use --device-type ios --wda-url http://192.168.1.10:8100 phone tap 540 960
```

---

## Actions

### tap

Taps a single point on the screen.

```
phone-use phone tap <x> <y> [--delay SECONDS]
```

| Argument | Type | Description |
|---|---|---|
| `x` | int | X coordinate in pixels |
| `y` | int | Y coordinate in pixels |
| `--delay` | float | Seconds to wait after the tap (default: 1.0) |

**When to use:**
- Pressing a button, link, or icon
- Opening an app from the home screen
- Selecting a list item or menu option
- Confirming a dialog

**Examples:**
```bash
# Tap the center of a 1080×1920 screen
phone-use phone tap 540 960

# Tap with a shorter delay when response is fast
phone-use phone tap 200 400 --delay 0.5

# Tap with a longer delay when the app loads slowly after tapping
phone-use phone tap 540 100 --delay 3.0
```

**Best practices:**
- Use `screenshot` first to confirm the element's coordinates before tapping.
- If the tap has no effect, the screen may still be loading — increase `--delay` or add a `back`/`home` reset and retry.
- For small touch targets (icons under ~60px), aim for the center of the element.

---

### double-tap

Taps the same point twice in quick succession (~100 ms apart).

```
phone-use phone double-tap <x> <y> [--delay SECONDS]
```

| Argument | Type | Description |
|---|---|---|
| `x` | int | X coordinate in pixels |
| `y` | int | Y coordinate in pixels |
| `--delay` | float | Seconds to wait after both taps |

**When to use:**
- Zooming in on a map or image
- Opening a file in some file managers
- Triggering double-tap gesture actions in apps (e.g. liking a post in Instagram)

**Examples:**
```bash
# Double-tap to zoom in on a map
phone-use phone double-tap 540 960

# Double-tap to like a photo
phone-use phone double-tap 540 700 --delay 0.5
```

**Best practices:**
- Most tappable UI elements respond to single tap. Reach for `double-tap` only when the app explicitly requires it.
- If the action isn't registering, check that no modal or overlay is covering the target.

---

### long-press

Presses and holds a point on the screen.

```
phone-use phone long-press <x> <y> [--duration-ms MS] [--delay SECONDS]
```

| Argument | Type | Description |
|---|---|---|
| `x` | int | X coordinate in pixels |
| `y` | int | Y coordinate in pixels |
| `--duration-ms` | int | Press duration in milliseconds (default: 3000) |
| `--delay` | float | Seconds to wait after the press |

**When to use:**
- Opening a context menu on an item (app icon, list entry, text selection)
- Activating drag-and-drop
- Selecting text by holding on a word
- Rearranging home screen icons

**Examples:**
```bash
# Long-press to open an app's context menu (1 second is usually enough)
phone-use phone long-press 200 400 --duration-ms 1000

# Long-press to select text (default 3 seconds)
phone-use phone long-press 540 600

# Long-press for drag preparation
phone-use phone long-press 150 900 --duration-ms 1500
```

**Best practices:**
- 1000–1500 ms is sufficient for most context menus. 3000 ms (the default) is conservative; reduce it to avoid triggering unintended behaviors.
- After a long-press that opens a menu, wait a moment before sending the next `tap` to select a menu item.

---

### swipe

Moves a finger from one coordinate to another.

```
phone-use phone swipe <start_x> <start_y> <end_x> <end_y> [--duration-ms MS] [--delay SECONDS]
```

| Argument | Type | Description |
|---|---|---|
| `start_x` | int | Start X in pixels |
| `start_y` | int | Start Y in pixels |
| `end_x` | int | End X in pixels |
| `end_y` | int | End Y in pixels |
| `--duration-ms` | int | Swipe speed in milliseconds (default: system default ~300 ms) |
| `--delay` | float | Seconds to wait after the swipe |

**When to use:**
- Scrolling a list or feed up or down
- Swiping between pages or tabs
- Pulling down the notification shade
- Dismissing a card or notification with a horizontal swipe
- Unlocking the screen (if no passcode)

**Common swipe directions:**

| Intent | start → end |
|---|---|
| Scroll down (content moves up) | `(540, 1500) → (540, 400)` |
| Scroll up (content moves down) | `(540, 400) → (540, 1500)` |
| Swipe right (go to previous page) | `(100, 960) → (900, 960)` |
| Swipe left (go to next page) | `(900, 960) → (100, 960)` |
| Pull down notification shade | `(540, 0) → (540, 800)` |

**Examples:**
```bash
# Scroll down a list
phone-use phone swipe 540 1500 540 400

# Scroll slowly (useful when triggering pull-to-refresh)
phone-use phone swipe 540 400 540 1000 --duration-ms 1200

# Dismiss a notification card by swiping right
phone-use phone swipe 540 300 1000 300 --duration-ms 200
```

**Best practices:**
- Keep start/end coordinates away from the very edges of the screen — edge zones are often reserved for system gestures (back, recent apps, notification shade).
- Slow swipes (`--duration-ms 800`+) are better for pull-to-refresh. Fast swipes (`--duration-ms 100–200`) feel more like flicks and trigger momentum scrolling.
- iOS does not have a hardware back button. Use a right-to-left swipe from the left edge (`swipe 0 500 350 500`) or the `back` action which does this automatically.

---

### type

Types text into the currently focused input field.

```
phone-use phone type "<text>"
```

| Argument | Type | Description |
|---|---|---|
| `text` | str | Text to type |

**When to use:**
- Filling in a search box, form field, or chat message after tapping on it
- Entering credentials (see security note below)
- Typing a URL in a browser address bar

**Examples:**
```bash
# Type a search query
phone-use phone type "best coffee shops near me"

# Type a URL
phone-use phone type "https://example.com"

# Type a multi-word name
phone-use phone type "John Smith"
```

**Workflow — always `tap` the field first:**
```bash
# 1. Focus the input field
phone-use phone tap 540 600

# 2. Type into it
phone-use phone type "hello world"
```

**Best practices:**
- Always `tap` the target input field before calling `type`. Text input is sent to whatever element currently has focus; if nothing is focused, the text is lost.
- On Android, `type` automatically switches to ADB Keyboard and restores the original IME afterward. Do not interrupt the sequence.
- On HarmonyOS, `type` uses the `uitest` text input directly — no IME switch needed.
- Use `clear` before `type` when you need to replace existing content rather than append to it.
- For multiline input (e.g. a chat message with line breaks), type each line and use the system enter key separately. The `\n` character is handled by the HDC backend natively but may not work as expected on ADB — compose the full text without newlines when possible.
- Avoid putting credentials in shell history. Use environment variables or a secrets manager and pass them through a wrapper script.

---

### clear

Clears all text in the currently focused input field.

```
phone-use phone clear
```

**When to use:**
- Resetting a search field before typing a new query
- Clearing a form field that already has content
- Removing text that `type` appended to instead of replacing

**Examples:**
```bash
# Clear and re-type a search field
phone-use phone tap 540 200
phone-use phone clear
phone-use phone type "new search query"
```

**Best practices:**
- `clear` works on the focused field. If focus has shifted (e.g. a dropdown appeared after a tap), the clear may go to the wrong element. Always verify with a `screenshot` when in doubt.
- On Android, `clear` sends `ADB_CLEAR_TEXT` broadcast. On iOS, it calls WDA's element clear endpoint. Both require an active focused element.

---

### back

Navigates back — presses the back button on Android/HarmonyOS or performs a left-edge swipe on iOS.

```
phone-use phone back [--delay SECONDS]
```

| Argument | Type | Description |
|---|---|---|
| `--delay` | float | Seconds to wait after the action |

**When to use:**
- Going back one screen in the navigation stack
- Dismissing a dialog or bottom sheet
- Closing a keyboard without confirming
- Returning from a detail view to a list view

**Examples:**
```bash
# Go back
phone-use phone back

# Go back and wait longer for the previous screen to load
phone-use phone back --delay 2.0
```

**Best practices:**
- Some apps override the back button to show "exit" confirmations — you may need two `back` calls to exit the app.
- On iOS, the left-edge swipe gesture may not work in all apps that use custom navigation. If `back` has no effect, tap the on-screen back button using `tap` with the button's coordinates.
- Pressing back from the root of an app typically returns to the home screen or triggers an exit dialog.

---

### home

Returns to the device's home screen.

```
phone-use phone home [--delay SECONDS]
```

| Argument | Type | Description |
|---|---|---|
| `--delay` | float | Seconds to wait after pressing home |

**When to use:**
- Returning to the launcher from any app
- Resetting context before starting a new flow
- Switching apps indirectly (home → tap another app icon)

**Examples:**
```bash
# Go to home screen
phone-use phone home

# Go home and wait for launcher to load
phone-use phone home --delay 1.5
```

**Best practices:**
- Prefer `home` over chaining multiple `back` calls when you want to get out of any app regardless of its navigation depth.
- After `home`, use `launch` to open a specific app rather than tapping its icon by coordinate — icon positions vary across devices and launchers.

---

### launch

Launches an app by name using the device's package manager.

```
phone-use phone launch "<app_name>" [--delay SECONDS]
```

| Argument | Type | Description |
|---|---|---|
| `app_name` | str | App name as listed in the supported apps config |
| `--delay` | float | Seconds to wait after launch (default: 1.0) |

**When to use:**
- Starting any session that involves a specific app
- Returning to an app after going home or running another app
- Opening a system app (Settings, Camera, Maps)

**Examples:**
```bash
# Launch WeChat
phone-use phone launch WeChat

# Launch Settings and wait for it to load
phone-use phone launch Settings --delay 2.0

# Launch on HarmonyOS
phone-use --device-type hdc phone launch 美团
```

**Finding installed app names:**
```bash
phone-use phone list-apps
phone-use --device-type hdc phone list-apps
phone-use --device-type ios phone list-apps
```

**Best practices:**
- App names are case-sensitive and must match the entries in the app config exactly. Run `phone list-apps` to confirm the exact name.
- Use `--delay 2.0` or higher for heavy apps (games, camera) that take longer to reach their initial screen.
- If an app is already running in the foreground, `launch` typically brings it to the foreground without restarting it. If you need a fresh launch, use `back`/`home` first or handle the running-app state manually.
- If `launch` returns an error, the app name is not in the supported list. Add it to the appropriate config file (`phone_agent/config/apps.py`, `apps_harmonyos.py`, or `apps_ios.py`).

---

### screenshot

Captures the current screen and saves it as a PNG file.

```
phone-use phone screenshot --output <path>
```

| Argument | Type | Description |
|---|---|---|
| `--output`, `-o` | str | File path to write the PNG (required) |

**When to use:**
- Inspecting the current screen state before deciding which coordinates to tap
- Debugging a sequence — take a screenshot between steps to see what happened
- Capturing evidence of a UI state
- Measuring element positions before hard-coding coordinates

**Examples:**
```bash
# Save to current directory
phone-use phone screenshot --output screen.png

# Short flag
phone-use phone screenshot -o /tmp/before_tap.png

# iOS screenshot
phone-use --device-type ios phone screenshot --output ios_screen.png
```

**Best practices:**
- Make `screenshot` the first command in any new automation sequence. Verify element positions before issuing `tap` or `swipe`.
- Use descriptive output filenames when capturing multiple states: `before.png`, `after_tap.png`.
- Screenshots are full-resolution PNGs. On high-density screens (3x), a 1080-wide logical view may produce a 3240-pixel PNG. The coordinates you pass to `tap`/`swipe` should always be in the device's **logical pixel** space (match what you see in `adb shell wm size`), not the physical PNG dimensions.
- On Android, if a screenshot is all-black, the screen may be locked or showing a secure screen (e.g. banking app). Unlock the device or navigate away from the secure view first.

---

### current-app

Prints the name of the currently active (foreground) app.

```
phone-use phone current-app
```

**When to use:**
- Verifying which app is in the foreground before issuing actions
- Debugging automation sequences where an unexpected app came to the front
- Checking whether a `launch` command succeeded and the app is running

**Examples:**
```bash
phone-use phone current-app
# Current app: WeChat

phone-use --device-type ios phone current-app
# Current app: Safari
```

**Best practices:**
- On Android, `current-app` parses `adb shell dumpsys window` and returns the focused package. On iOS it queries WDA's `activeAppInfo` endpoint. If the result is unexpected, follow up with `screenshot` to see the actual screen.
- Use `current-app` at the start of a script to assert you're in the right app before doing destructive actions.

---

## Coordinate System

All coordinates passed to `tap`, `double-tap`, `long-press`, and `swipe` are **absolute pixels** in the device's logical resolution.

**Finding your device's resolution:**
```bash
# Android / HarmonyOS
adb shell wm size
# → Physical size: 1080x2400

# iOS — check in Settings > General > About, or use screenshot dimensions
phone-use --device-type ios phone screenshot -o tmp.png
python3 -c "from PIL import Image; img=Image.open('tmp.png'); print(img.size)"
```

**iOS scale factor note:** WebDriverAgent operates in logical points (device-independent pixels). The `xctest` backend internally divides coordinates by a scale factor of 3, so pass raw pixel coordinates as you would for ADB and the backend handles the conversion.

**Quick reference — common resolutions:**

| Device class | Resolution | Center |
|---|---|---|
| Android 1080p | 1080 × 1920 | (540, 960) |
| Android 1080p tall | 1080 × 2400 | (540, 1200) |
| iPhone 14 Pro | 1179 × 2556 | (590, 1278) |
| iPhone SE (3rd gen) | 750 × 1334 | (375, 667) |

---

## Best Practices

### Sequence design

**Always verify before acting.** Take a `screenshot` before tapping anything, especially in a new flow or after a `launch`. An app's UI can vary based on state, account settings, or OS version.

```bash
phone-use phone launch WeChat
phone-use phone screenshot -o state.png
# inspect state.png → then decide the tap coordinates
phone-use phone tap 540 200
```

**Add delays generously at first.** Network-dependent screens, animations, and transitions take time. Use `--delay 2.0` while developing; tune down to `--delay 0.5` once the sequence is stable.

**Use `home` to reset.** When a sequence fails partway through, `home` returns to a known state more reliably than backtracking with `back`.

```bash
phone-use phone home
phone-use phone launch <app>
# ...retry the sequence
```

### Reliability

**Don't hard-code coordinates without verifying.** Screen layouts change with OS updates, font size settings, and app versions. Re-run `screenshot` and re-measure when a sequence stops working.

**Handle text input carefully.** Always `tap` the field, then `clear`, then `type`. Skipping `clear` will append to whatever is already in the field.

```bash
phone-use phone tap 540 600     # focus the field
phone-use phone clear           # remove existing content
phone-use phone type "my text"  # type fresh content
```

**Prefer `launch` over tapping app icons.** Icon positions shift when apps are installed or the launcher is reorganized. `launch` uses the package name and is stable.

### Scripting

**Chain commands in a shell script for repeatable flows:**

```bash
#!/bin/bash
set -e

DEVICE_FLAGS="--device-type adb"

phone-use $DEVICE_FLAGS phone home
phone-use $DEVICE_FLAGS phone launch Maps
sleep 2
phone-use $DEVICE_FLAGS phone tap 540 180     # tap search bar
phone-use $DEVICE_FLAGS phone type "coffee"
phone-use $DEVICE_FLAGS phone screenshot -o result.png
```

**Use `set -e`** so the script stops on the first failed command rather than proceeding into an undefined state.

**Capture intermediate screenshots** for debugging. Name them with a step number or timestamp:

```bash
phone-use phone screenshot -o "step_01_home.png"
phone-use phone launch WeChat
phone-use phone screenshot -o "step_02_wechat_open.png"
```

### Multi-device

When multiple devices are connected, always specify `--device-id` to avoid ambiguity:

```bash
# List devices first
phone-use --list-devices

# Then pin the target device
phone-use --device-id R58M12345 phone screenshot -o screen.png
```

### iOS-specific

- WDA must be running before any `phone` command. Check with `phone-use --device-type ios --wda-status`.
- Port forwarding is required for USB-connected devices: `iproxy 8100 8100`.
- iOS does not have a hardware back button. The `back` action performs a left-edge swipe. For apps that don't support this gesture, `tap` the on-screen back arrow directly.
- `type` on iOS sends keystrokes through WDA at a configurable frequency. If characters are dropped, the field may be updating (e.g. autocomplete) faster than input arrives — add a `--delay` before typing.
