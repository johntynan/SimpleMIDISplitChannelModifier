#!/usr/bin/env bash

echo "=== MIDI + Tkinter Environment Setup ==="

# 1. Install system dependencies for python-rtmidi
echo "Installing system dependencies..."
sudo apt update
sudo apt install -y build-essential libasound2-dev libjack-dev

# 2. Install Tkinter if missing
echo "Checking for Tkinter..."
python3 - << 'EOF'
try:
    import tkinter
    print("✓ Tkinter is already installed.")
except Exception:
    print("✗ Tkinter missing. Will install python3-tk.")
EOF

sudo apt install -y python3-tk

# 3. Create virtual environment if missing
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# 4. Activate venv
echo "Activating virtual environment..."
source venv/bin/activate

# 5. Install Python packages
echo "Installing Python packages..."
pip install --upgrade pip
pip install mido python-rtmidi

# 6. Diagnostic check
echo "=== Running diagnostics ==="
python3 - << 'EOF'
print("Checking mido...")
try:
    import mido
    print("  ✓ mido version:", mido.__version__)
except Exception as e:
    print("  ✗ mido import failed:", e)

print("\nChecking python-rtmidi...")
try:
    import rtmidi
    print("  ✓ python-rtmidi imported successfully")
except Exception as e:
    print("  ✗ python-rtmidi import failed:", e)

print("\nChecking Tkinter...")
try:
    import tkinter
    print("  ✓ Tkinter imported successfully")
except Exception as e:
    print("  ✗ Tkinter import failed:", e)

print("\nChecking MIDI ports...")
try:
    import mido
    print("  Input ports:", mido.get_input_names())
    print("  Output ports:", mido.get_output_names())
except Exception as e:
    print("  ✗ Error listing ports:", e)

print("\nDiagnostics complete.\n")
EOF

# 7. Run your script
echo "=== Launching MidiRouter.py ==="
python3 MidiFilter.py
