---
name: phone-use
description: Automates phone interactions for web testing, screenshots, or any direct mobile interaction. Use when a task needs to interact with a real mobile device through Android (ADB), HarmonyOS (HDC), or iOS.
---

# Phone Automation with phone-use CLI

The `phone-use` command provides direct device control from the command line. Unlike an agent loop, each command maps 1-to-1 to a device action, so you compose reliable mobile workflows step by step.

```bash
phone-use [DEVICE FLAGS] phone <action> [ACTION FLAGS]
```

## Prerequisites

Before using this skill, the device backend must already be installed and working.

| Device | Requirement |
|---|---|
| Android (ADB) | `adb` installed, USB debugging enabled, ADB Keyboard APK installed |
| HarmonyOS (HDC) | `hdc` installed, USB debugging enabled |
| iOS | `libimobiledevice` installed, WebDriverAgent running, port forwarding active |

Verify the setup first:

```bash
phone-use --list-devices
phone-use --device-type ios --wda-status
```

## Core Workflow

1. **Reset**: `phone-use phone home` to start from a known state
2. **Open target app**: `phone-use phone launch "App Name"`
3. **Inspect**: `phone-use phone screenshot -o screen.png` and/or `phone-use phone state`
4. **Interact**: use gestures and input commands like `tap`, `swipe`, `type`
5. **Verify**: run `screenshot`, `state`, or `current-app` after important steps
6. **Recover**: use `back` or `home` when the flow drifts off course

## Device Backends

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

- `adb`: default Android backend
- `hdc`: HarmonyOS backend
- `ios`: iOS backend through WebDriverAgent

## Device Flags

These flags go before `phone` and apply to every action.

| Flag | Default | Description |
|---|---|---|
| `--device-type adb|hdc|ios` | `adb` | Selects the device backend |
| `--device-id <id>` | auto-detect | ADB serial, HDC target, or iOS UDID |
| `--wda-url <url>` | `http://localhost:8100` | WebDriverAgent base URL for iOS |

## Essential Commands

```bash
# Navigation and app control
phone-use phone home
phone-use phone back
phone-use phone launch "Settings"
phone-use phone current-app

# Screen inspection
phone-use phone screenshot -o screen.png
phone-use phone state
phone-use phone state --output state.json

# Touch gestures
phone-use phone tap 540 960
phone-use phone double-tap 540 960
phone-use phone long-press 540 960 --duration-ms 1200
phone-use phone swipe 540 1500 540 400

# Text input
phone-use phone clear
phone-use phone type "hello world"
```

## Commands by Purpose

### App Control and Navigation

Use these commands to move between screens, reset state, and open apps.

```bash
phone-use phone home [--delay SECONDS]
phone-use phone back [--delay SECONDS]
phone-use phone launch "<app_name>" [--delay SECONDS]
phone-use phone current-app
```

#### `home`

Returns to the device home screen.

**Use when:**
- Starting any new task
- Resetting the phone to a known state
- Exiting an unknown app flow quickly

**Examples:**

```bash
phone-use phone home
phone-use phone home --delay 1.5
```

**Best practices:**
- Start new flows with `home`.
- Prefer `home` over repeated `back` calls when recovery matters more than preserving app state.
- After `home`, prefer `launch` over tapping app icons by coordinate.

#### `back`

Navigates backward. On Android and HarmonyOS it presses the system back button. On iOS it performs a left-edge swipe.

**Use when:**
- Returning one screen in the current flow
- Dismissing dialogs or sheets
- Closing the keyboard without submitting

**Examples:**

```bash
phone-use phone back
phone-use phone back --delay 2.0
```

**Best practices:**
- Some apps intercept back and show an exit confirmation.
- On iOS, custom navigation may require tapping the on-screen back button instead.

#### `launch`

Launches an app by name from the supported app config.

```bash
phone-use phone launch "<app_name>" [--delay SECONDS]
```

**Use when:**
- Starting work in a specific app
- Returning to an app after `home`
- Opening system apps like Settings or Camera

**Examples:**

```bash
phone-use phone launch WeChat
phone-use phone launch Settings --delay 2.0
phone-use --device-type hdc phone launch 美团
```

Find installed app names:

```bash
phone-use phone list-apps
phone-use --device-type hdc phone list-apps
phone-use --device-type ios phone list-apps
```

Add friendly names for `list-apps` and `launch`:

```python
# Android: phone_agent/config/apps.py
APP_PACKAGES["My App"] = "com.example.myapp"

# HarmonyOS: phone_agent/config/apps_harmonyos.py
APP_PACKAGES["My App"] = "com.example.myapp"

# iOS: phone_agent/config/apps_ios.py
APP_PACKAGES_IOS["My App"] = "com.example.myapp"
```

After adding the mapping, `phone-use phone list-apps` will show `My App` instead of only the raw package or bundle id when that app is installed on the device, and `phone-use phone launch "My App"` will work with the same name.

For HarmonyOS, add an ability override too when the app does not start with the default `EntryAbility`:

```python
# phone_agent/config/apps_harmonyos.py
APP_ABILITIES["com.example.myapp"] = "MainAbility"
```

**Best practices:**
- App names are case-sensitive.
- Use longer delays for heavy apps.
- If the app name is missing, add it to the relevant app config.

#### `current-app`

Prints the current foreground app.

```bash
phone-use phone current-app
```

**Use when:**
- Verifying where the flow landed
- Checking whether `launch` succeeded
- Guarding destructive actions

### Screen Inspection and Verification

Use these commands before and after actions to confirm the visual and structural state of the phone.

```bash
phone-use phone screenshot --output <path>
phone-use phone state [--output <path>]
```

#### `screenshot`

Captures the current screen as a PNG.

```bash
phone-use phone screenshot --output <path>
```

**Use when:**
- Confirming what the device currently shows
- Measuring coordinates before tapping
- Capturing evidence of a UI state

**Examples:**

```bash
phone-use phone screenshot --output screen.png
phone-use phone screenshot -o /tmp/before_tap.png
phone-use --device-type ios phone screenshot --output ios_screen.png
```

**Best practices:**
- Use descriptive filenames like `before.png` and `after_login.png`.
- Coordinates for actions should use logical device pixels, not raw PNG dimensions.
- If the screenshot is black on Android, the screen may be locked or secure.

#### `state`

Prints a structured summary of the current native UI hierarchy. With `--output`, it also saves the raw JSON payload.

```bash
phone-use phone state [--output <path>]
```

**Use when:**
- You need structure, labels, ids, or bounds
- A screenshot is not enough to identify the right target
- You want a saved UI hierarchy for later debugging

**Examples:**

```bash
phone-use phone state
phone-use phone state --output phone_state.json
phone-use --device-type ios phone state --output ios_state.json
```

**Best practices:**
- Think of `state` like a DOM or accessibility snapshot.
- Use `screenshot` for what is visually rendered and `state` for what the platform exposes.
- HarmonyOS/HDC does not currently support `state`.

### Touch Gestures

Use these commands for coordinate-based interaction on the device screen.

```bash
phone-use phone tap <x> <y> [--delay SECONDS]
phone-use phone double-tap <x> <y> [--delay SECONDS]
phone-use phone long-press <x> <y> [--duration-ms MS] [--delay SECONDS]
phone-use phone swipe <start_x> <start_y> <end_x> <end_y> [--duration-ms MS] [--delay SECONDS]
```

#### `tap`

Taps a single point on the screen.

**Use when:**
- Pressing a button, icon, link, or list item
- Confirming a dialog
- Focusing an input field before typing

**Examples:**

```bash
phone-use phone tap 540 960
phone-use phone tap 200 400 --delay 0.5
phone-use phone tap 540 100 --delay 3.0
```

**Best practices:**
- Use `screenshot` first when coordinates are uncertain.
- Increase `--delay` if nothing happens because the UI is still loading.
- Aim for the center of small targets.

#### `double-tap`

Taps the same point twice in quick succession.

**Use when:**
- Triggering zoom gestures
- Activating app-specific double-tap actions

**Examples:**

```bash
phone-use phone double-tap 540 960
phone-use phone double-tap 540 700 --delay 0.5
```

**Best practices:**
- Prefer `tap` unless the app clearly expects a double tap.
- Re-check the screen if the gesture does not register.

#### `long-press`

Presses and holds a point on the screen.

**Use when:**
- Opening context menus
- Preparing for drag-and-drop
- Selecting text

**Examples:**

```bash
phone-use phone long-press 200 400 --duration-ms 1000
phone-use phone long-press 540 600
phone-use phone long-press 150 900 --duration-ms 1500
```

**Best practices:**
- `1000-1500 ms` is enough for most context menus.
- Wait briefly after the press before tapping a menu item.

#### `swipe`

Moves a finger from one coordinate to another.

**Use when:**
- Scrolling lists or feeds
- Moving between pages or tabs
- Pulling system panels or dismissing cards

**Examples:**

```bash
phone-use phone swipe 540 1500 540 400
phone-use phone swipe 540 400 540 1000 --duration-ms 1200
phone-use phone swipe 540 300 1000 300 --duration-ms 200
```

Common swipe directions:

| Intent | start -> end |
|---|---|
| Scroll down (content moves up) | `(540, 1500) -> (540, 400)` |
| Scroll up (content moves down) | `(540, 400) -> (540, 1500)` |
| Swipe right | `(100, 960) -> (900, 960)` |
| Swipe left | `(900, 960) -> (100, 960)` |
| Pull notification shade | `(540, 0) -> (540, 800)` |

**Best practices:**
- Avoid very edge-heavy coordinates because they may trigger system gestures.
- Use longer durations for pull-to-refresh and shorter durations for flick-like motion.
- On iOS, `back` uses the same left-edge gesture pattern.

### Text Input

Use these commands after focusing a text field.

```bash
phone-use phone clear
phone-use phone type "<text>"
```

#### `type`

Types text into the currently focused input field.

```bash
phone-use phone type "<text>"
```

**Use when:**
- Filling forms
- Typing search queries or URLs
- Entering messages or short text content

**Examples:**

```bash
phone-use phone type "best coffee shops near me"
phone-use phone type "https://example.com"
phone-use phone type "John Smith"
```

Recommended workflow:

```bash
phone-use phone tap 540 600
phone-use phone clear
phone-use phone type "hello world"
```

**Best practices:**
- Always focus the field first.
- Use `clear` when replacing existing text.
- Avoid putting secrets directly in shell history.
- On Android, do not interrupt the temporary IME switch.

#### `clear`

Clears the currently focused input field.

```bash
phone-use phone clear
```

**Use when:**
- Resetting a search field
- Replacing an existing value
- Recovering from appended text

**Examples:**

```bash
phone-use phone tap 540 200
phone-use phone clear
phone-use phone type "new search query"
```

**Best practices:**
- Make sure the correct field still has focus.
- If focus may have changed, verify with `screenshot` first.

## Coordinate System

All coordinates passed to `tap`, `double-tap`, `long-press`, and `swipe` are absolute values in the device's logical resolution.

Find the resolution:

```bash
# Android / HarmonyOS
adb shell wm size

# iOS
phone-use --device-type ios phone screenshot -o tmp.png
python3 -c "from PIL import Image; img=Image.open('tmp.png'); print(img.size)"
```

Quick reference:

| Device class | Resolution | Center |
|---|---|---|
| Android 1080p | 1080 x 1920 | (540, 960) |
| Android 1080p tall | 1080 x 2400 | (540, 1200) |
| iPhone 14 Pro | 1179 x 2556 | (590, 1278) |
| iPhone SE (3rd gen) | 750 x 1334 | (375, 667) |

For iOS, pass pixel-style coordinates the same way you would for ADB; the backend handles scale conversion internally.

## Common Workflows

### Starting a Stable Flow

```bash
phone-use phone home
phone-use phone launch WeChat --delay 2.0
phone-use phone screenshot -o step_01_open.png
phone-use phone state --output step_01_open.json
```

### Searching in an App

```bash
phone-use phone tap 540 180
phone-use phone clear
phone-use phone type "coffee"
phone-use phone screenshot -o step_02_search.png
```

### Recovering from a Bad State

```bash
phone-use phone current-app
phone-use phone back --delay 1.0
phone-use phone home
phone-use phone launch Maps --delay 2.0
```

### Multi-device Targeting

```bash
phone-use --list-devices
phone-use --device-id R58M12345 phone screenshot -o screen.png
```

## Tips

1. Always inspect before acting: use `screenshot` first, then `state` when you need structure.
2. Start with generous delays like `--delay 2.0`, then tighten after the flow is stable.
3. Prefer `launch` over tapping app icons.
4. Use `home` as the fastest reset path when a sequence fails.
5. Capture intermediate screenshots during scripting so failures are easier to debug.
6. When multiple devices are attached, always pin `--device-id`.

## Troubleshooting

**No device found?**

```bash
phone-use --list-devices
```

**iOS commands failing?**

```bash
phone-use --device-type ios --wda-status
iproxy 8100 8100
```

**Tap or swipe has no effect?**

```bash
phone-use phone screenshot -o current.png
phone-use phone state --output current.json
```

The UI may still be loading, the coordinates may be wrong, or a modal may be covering the target.

**Text went to the wrong place?**

Tap the field again, clear it, and retry:

```bash
phone-use phone tap 540 600
phone-use phone clear
phone-use phone type "retry text"
```

## iOS Notes

- WebDriverAgent must already be running.
- USB-connected devices usually need port forwarding through `iproxy 8100 8100`.
- `back` is implemented as a left-edge swipe and may not work in every custom app.
- If typed characters drop, add a short wait before calling `type`.
