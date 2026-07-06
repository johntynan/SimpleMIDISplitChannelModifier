# SimpleMIDISplitChannelModifier / MidiModifier  
*A Raspberry Pi–optimized MIDI routing and performance tool*

SimpleMIDISplitChannelModifier (also known as **MidiModifier**) is a touchscreen‑friendly MIDI router designed for Raspberry Pi systems with small 480×320 displays. It provides real‑time MIDI monitoring, split‑point routing, GM/GS instrument control, drumkit selection, program changes, and JSON‑based song presets and setlists — all inside a compact multi‑tab Tkinter GUI.

![App Screenshot](Images/MidiModifierScreenshot.png)

---

# Quick Start (Windows, macOS, Linux)

1. Download the project  
You may either clone the repository:

```
git clone https://github.com/johntynan/SimpleMIDISplitChannelModifier.git
cd SimpleMIDISplitChannelModifier
```

Or download the ZIP from GitHub, extract it, and open a terminal or command prompt inside the extracted folder.

2. Create a virtual environment (recommended)

Windows:
```
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies
```
pip install mido python-rtmidi
```

4. Run the application

Windows:
```
python MidiModifier.py
```

macOS / Linux:
```
python3 MidiModifier.py
```

Or on macOS/Linux you may use the helper script:
```
chmod +x run_midimodifier.sh
./run_midimodifier.sh
```

Once launched, select your MIDI ports, set your split point, and begin routing.

---

# Overview

SimpleMIDISplitChannelModifier is a lightweight, cross‑platform MIDI router that provides:

- A configurable split point for dividing the keyboard into zones  
- Independent routing for Lower and Upper zones  
- Per‑zone channel remapping  
- Real‑time Incoming and Outgoing MIDI monitoring  
- Safe fallback behavior when no ports are selected  
- A thread‑safe routing loop for stable live performance  
- Compatibility with Windows, macOS, Linux, and Raspberry Pi  
- GM instrument definitions, GS bank support, drumkit selection  
- Song presets and setlists for live performance workflows  

Main script: `MidiModifier.py`  
Helper script (Unix-like systems): `run_midimodifier.sh`

---

# Features

## Core Routing
- Adjustable split point  
- Lower/Upper zone routing  
- Per‑zone transpose  
- Per‑zone channel override  
- Per‑zone output port selection  
- Non‑note messages broadcast to both ports  

## Monitoring
- Real‑time Incoming MIDI view  
- Real‑time Outgoing MIDI view  
- Per‑zone status lines showing incoming/outgoing notes  

## GM / GS Support
- GM instrument definition files (`*.gm.json`)  
- Program Change for Lower/Upper zones  
- GS Bank Select (MSB/LSB)  
- GS Program Change  
- GS Reset SysEx  

## Drumkits
- Drumkit definition files (`*drumkits.gm.json`)  
- Drumkit program selection  
- Drumkit MIDI channel selection  
- GS-compatible drumkit bank messages  

## Presets & Setlists
- Save/load/delete song presets  
- Presets store all routing parameters  
- Create/update/delete setlists  
- Start setlist playback  
- Advance to next song  

## Safety & Performance
- Panic button (All Notes Off + Reset Controllers)  
- Thread‑safe routing loop  
- Safe fallback when no ports selected  
- Optimized for Raspberry Pi touchscreens  

---

# Hardware Requirements

- Raspberry Pi 3 / 4 / Zero 2 (optional)  
- 480×320 touchscreen (Waveshare, PiTFT, etc.)  
- USB MIDI keyboard, drum module, or controller  
- Optional: Roland GS/SC‑55/SC‑88 compatible synth  
- Optional: GM instrument definition JSON files  
- Optional: GM drumkit definition JSON files  

---

# Installation (Detailed)

## Windows / macOS / Linux

### Create a virtual environment

Windows:
```
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
```

### Install dependencies

```
pip install mido python-rtmidi
```

### Run the application

Windows:
```
python MidiModifier.py
```

macOS / Linux:
```
python3 MidiModifier.py
```

### Optional: Use the launcher script (macOS/Linux)

```
chmod +x run_midimodifier.sh
./run_midimodifier.sh
```

---

# Running on Raspberry Pi

The GUI automatically scales for 480×320 touchscreens using `ui_scale()`.

Recommended packages:

```
sudo apt install python3 python3-pip python3-tk python3-rtmidi
```

Run:

```
python3 MidiModifier.py
```

---

# MIDI Routing Logic

Routing is based on a **split point**:

- Notes ≤ split point → Lower zone  
- Notes > split point → Upper zone  

Each zone has:

- Independent transpose  
- Independent MIDI channel  
- Independent output port  

Non‑note messages (pitch bend, CC, aftertouch, etc.) are sent to **both** output ports.

---

# GM Instrument Definitions

GM instrument definition files (`*.gm.json`) map program numbers to instrument names:

```json
{
  "0": "Acoustic Grand Piano",
  "1": "Bright Piano",
  "2": "Electric Grand"
}
```

These files populate the Program Change dropdowns.

---

# Drumkit Definitions

Drumkit definition files (`*drumkits.gm.json`) map program numbers to drumkits:

```json
{
  "0": "Standard Kit",
  "8": "Room Kit",
  "16": "Power Kit"
}
```

GS‑compatible drumkits (SC‑55/SC‑88) automatically send Bank Select MSB/LSB.

---

# GS Support

### GS Bank Select
- CC0 → Bank MSB  
- CC32 → Bank LSB  

### GS Program Change
Sent after Bank Select.

### GS Reset SysEx
Resets GS‑compatible devices to default state.

---

# Song Presets

Song presets store **all routing parameters**, including:

- Split point  
- Transpose  
- Channels  
- Ports  
- Instrument files  
- Program numbers  
- GS bank values  
- Drumkit file + selection  
- Drumkit channel  

Presets are saved in:

```
midimodifier_songs.json
```

---

# Setlists

Setlists are ordered lists of song presets:

```json
{
  "setlists": {
    "My Setlist": ["Intro", "Verse", "Chorus"]
  }
}
```

You can:

- Create/update/delete setlists  
- Start a setlist  
- Advance to the next song  

Perfect for live performance.

---

# Panic Button

Sends the following on **all 16 channels**:

- CC123 — All Notes Off  
- CC64 — Sustain Off  
- CC121 — Reset All Controllers  

Useful for stuck notes or runaway sustain.

---

# Troubleshooting

### No MIDI ports appear
- Ensure your MIDI devices or virtual ports are active before launching.

### Permission errors (macOS/Linux)
```
chmod +x run_midimodifier.sh
```
Use sudo only if necessary.

### Python not found
- Windows: ensure Python is added to PATH  
- macOS/Linux: use `python3` instead of `python`

---

# File Structure

```
SimpleMIDISplitChannelModifier/
│
├── MidiModifier.py            # Main application
├── run_midimodifier.sh        # Launcher script
├── *.gm.json                  # GM instrument definitions
├── *drumkits.gm.json          # Drumkit definitions
├── midimodifier_songs.json    # Presets + setlists
├── Images/                    # Screenshots
└── README.md                  # Project documentation
```

---

# License

MIT License (recommended for open‑source hardware/software tools)
