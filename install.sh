#!/usr/bin/env bash
# install.sh — one-time setup for phone-use CLI
#
# Usage:
#   ./install.sh            # global install (recommended)
#   ./install.sh --local    # install into the current Python environment
#   ./install.sh --dev      # local editable install with dev dependencies
#   ./install.sh --global   # explicit global install
#
# After this runs, `phone-use` is available on your PATH.

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
        echo "==> Installing phone-use globally with uv..."
        uv tool install --force "$SCRIPT_DIR"
    elif [[ $DEV -eq 1 ]]; then
        echo "==> Installing package + dev dependencies locally with uv..."
        uv pip install -e ".[dev]"
    else
        echo "==> Installing package locally with uv..."
        uv pip install -e .
    fi
else
    if [[ "$MODE" == "global" ]]; then
        echo "==> Installing phone-use globally with pip --user..."
        pip3 install --user "$SCRIPT_DIR"
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
if command -v phone-use &>/dev/null; then
    echo "==> phone-use installed at: $(which phone-use)"
else
    # Entry point may not be on PATH yet — check common locations
    VENV_BIN=""
    if [[ -f "$HOME/.local/bin/phone-use" ]]; then
        VENV_BIN="$HOME/.local/bin"
    elif [[ -f "$SCRIPT_DIR/.venv/bin/phone-use" ]]; then
        VENV_BIN="$SCRIPT_DIR/.venv/bin"
    fi

    if [[ -n "$VENV_BIN" ]]; then
        echo "==> phone-use installed at: $VENV_BIN/phone-use"
        echo
        echo "    It is not on your PATH yet. Add it:"
        echo
        if [[ "$VENV_BIN" == "$HOME/.local/bin" ]]; then
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
fi

echo
echo "==> Quick test:"
echo "      phone-use --help"
echo "      phone-use phone --help"
echo "      phone-use phone screenshot --output screen.png"
echo
echo "    Done."
