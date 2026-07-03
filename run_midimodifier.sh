#!/bin/bash
set -e

echo "=== MIDI Router Launcher ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# -------------------------------
# 1. Ensure Python 3.12 exists
# -------------------------------
if ! command -v python3.12 >/dev/null 2>&1; then
    echo "ERROR: python3.12 is not installed."
    echo "Install it with:"
    echo "  sudo apt install python3.12 python3.12-venv python3.12-tk"
    exit 1
fi

PY=python3.12

echo "Using Python: $($PY -V)"

# -------------------------------
# 2. Recreate venv if missing or wrong version
# -------------------------------
if [ ! -d "venv" ]; then
    echo "Creating new Python 3.12 venv..."
    $PY -m venv venv
fi

# Check venv Python version
VENV_PY="./venv/bin/python"
VENV_VERSION="$($VENV_PY -V 2>/dev/null || echo 'NONE')"

if [[ "$VENV_VERSION" != *"3.12"* ]]; then
    echo "Venv is wrong version ($VENV_VERSION). Recreating..."
    rm -rf venv
    $PY -m venv venv
fi

source venv/bin/activate

# -------------------------------
# 3. Install required packages
# -------------------------------
echo "Installing Python packages..."
pip install --upgrade pip
pip install mido python-rtmidi

# -------------------------------
# 4. Diagnostics
# -------------------------------
echo "=== Running diagnostics ==="

echo "Python version: $($VENV_PY -V)"
echo "Mido location: $(python - <<EOF
import mido, sys
print(mido.__file__)
EOF
)"

# Check Tkinter
echo "Checking Tkinter..."
python - <<EOF
try:
    import tkinter
    print("Tkinter OK")
except Exception as e:
    print("Tkinter ERROR:", e)
EOF

# -------------------------------
# 5. Launch the router
# -------------------------------
echo "=== Launching MidiModifier.py ==="
exec python MidiModifier.py
