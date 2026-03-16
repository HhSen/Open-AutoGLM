#!/usr/bin/env bash
# install.sh — one-time setup for phone-use CLI
#
# Usage:
#   ./install.sh            # global editable install (recommended)
#   ./install.sh --local    # install into the current Python environment
#   ./install.sh --dev      # local editable install with dev dependencies
#   ./install.sh --global   # explicit global install
#
# After this runs, `phone-use` is available on your PATH.
# In global mode with uv/pip, the install is editable so the CLI tracks this
# repository's current source instead of a cached snapshot.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV=0
MODE="global"
for arg in "$@"; do
    [[ "$arg" == "--dev" ]] && DEV=1
    [[ "$arg" == "--local" ]] && MODE="local"
    [[ "$arg" == "--global" ]] && MODE="global"
done

if [[ $DEV -eq 1 ]]; then
    MODE="local"
fi

echo "==> Setting up phone-use CLI"
echo "    Project: $SCRIPT_DIR"
echo

# ── Detect installer ──────────────────────────────────────────────────────────
if command -v uv &>/dev/null; then
    INSTALLER="uv"
    echo "==> Found uv $(uv --version | head -1 | awk '{print $2}')"
elif command -v pip3 &>/dev/null; then
    INSTALLER="pip"
    echo "==> uv not found, falling back to pip"
    echo "    (Install uv for faster setup: curl -Lsf https://astral.sh/uv/install.sh | sh)"
else
    echo "ERROR: Neither uv nor pip3 found. Install Python 3.10+ first."
    exit 1
fi

# ── Install the package ───────────────────────────────────────────────────────
cd "$SCRIPT_DIR"

if [[ "$INSTALLER" == "uv" ]]; then
    if [[ "$MODE" == "global" ]]; then
        echo "==> Installing phone-use globally with uv (editable, tracks repo changes)..."
        uv tool install --force --editable "$SCRIPT_DIR"
    elif [[ $DEV -eq 1 ]]; then
        echo "==> Installing package + dev dependencies locally with uv..."
        uv pip install -e ".[dev]"
    else
        echo "==> Installing package locally with uv..."
        uv pip install -e .
    fi
else
    if [[ "$MODE" == "global" ]]; then
        echo "==> Installing phone-use globally with pip --user (editable, tracks repo changes)..."
        pip3 install --user -e "$SCRIPT_DIR"
    elif [[ $DEV -eq 1 ]]; then
        echo "==> Installing package + dev dependencies locally with pip..."
        pip3 install -e ".[dev]"
    else
        echo "==> Installing package locally with pip..."
        pip3 install -e .
    fi
fi

# ── Verify the entry point ────────────────────────────────────────────────────
echo
ACTIVE_BIN="$(command -v phone-use 2>/dev/null || true)"
GLOBAL_BIN=""
LOCAL_BIN=""

if [[ -f "$HOME/.local/bin/phone-use" ]]; then
    GLOBAL_BIN="$HOME/.local/bin/phone-use"
fi

if [[ -f "$SCRIPT_DIR/.venv/bin/phone-use" ]]; then
    LOCAL_BIN="$SCRIPT_DIR/.venv/bin/phone-use"
fi

if [[ "$MODE" == "global" && -n "$GLOBAL_BIN" ]]; then
    echo "==> Global phone-use installed at: $GLOBAL_BIN"
    if [[ -n "$ACTIVE_BIN" && "$ACTIVE_BIN" != "$GLOBAL_BIN" ]]; then
        echo "    Note: your current shell resolves 'phone-use' to: $ACTIVE_BIN"
        echo "    The global CLI is installed correctly, but another install is shadowing it on PATH."
    fi
elif [[ -n "$ACTIVE_BIN" ]]; then
    echo "==> phone-use installed at: $ACTIVE_BIN"
elif [[ -n "$GLOBAL_BIN" || -n "$LOCAL_BIN" ]]; then
    RESOLVED_BIN="$GLOBAL_BIN"
    if [[ -z "$RESOLVED_BIN" ]]; then
        RESOLVED_BIN="$LOCAL_BIN"
    fi
    echo "==> phone-use installed at: $RESOLVED_BIN"
    echo
    echo "    It is not on your PATH yet. Add it:"
    echo
    if [[ -n "$GLOBAL_BIN" ]]; then
        echo "      export PATH=\"$HOME/.local/bin:\$PATH\""
        echo "      # Add that line to your ~/.zshrc or ~/.bashrc to make it permanent."
    else
        echo "      # activate the project venv:"
        echo "      source $SCRIPT_DIR/.venv/bin/activate"
    fi
else
    echo "WARNING: phone-use was not found after installation."
    echo "  If you used global install, add ~/.local/bin to PATH."
    echo "  If you used local install, activate: source $SCRIPT_DIR/.venv/bin/activate"
fi

echo
echo "==> Quick test:"
echo "      phone-use --help"
echo "      phone-use phone --help"
echo "      phone-use phone screenshot --output screen.png"
echo
echo "    Done."
