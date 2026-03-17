#!/usr/bin/env bash

echo "=== MIDI + Tkinter Environment Setup ==="

# 1. System dependencies
echo "Installing system dependencies..."
sudo apt update
sudo apt install -y build-essential libasound2-dev libjack-dev python3-tk

# 2. Create venv if missing
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Define venv executables
VENV_PYTHON="venv/bin/python3"
VENV_PIP="venv/bin/pip"

# 3. Upgrade pip inside venv
echo "Upgrading pip..."
$VENV_PIP install --upgrade pip

# 4. Install Python packages inside venv
echo "Installing Python packages..."
$VENV_PIP install mido python-rtmidi

# 5. Diagnostics
echo "=== Running diagnostics ==="
$VENV_PYTHON - << 'EOF'
import mido, tkinter
print("✓ mido:", mido.__version__)
print("✓ python-rtmidi imported")
print("✓ Tkinter imported")
print("Input ports:", mido.get_input_names())
print("Output ports:", mido.get_output_names())
EOF

# 6. Run your script
echo "=== Launching MidiModifier.py ==="
$VENV_PYTHON MidiModifier.py
