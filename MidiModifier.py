"""
# MidiModifier — Raspberry Pi MIDI Router

MidiModifier is a touchscreen‑friendly MIDI routing and performance tool
designed for Raspberry Pi systems with small displays (typically 480×320).
It provides:

- Real‑time MIDI monitoring  
- Split‑point based routing (lower/upper zones)  
- Transposition per zone  
- Program Change, GS Bank Select, Drumkit selection  
- JSON‑based song presets and setlists  
- Support for General MIDI and GS instrument definition files  
- A multi‑tab Tkinter GUI optimized for live performance  

This file contains the full application logic, including:

- MIDI routing loop  
- GUI construction  
- Instrument/drumkit loaders  
- GS support  
- Song preset and setlist management  
- Panic/reset utilities  

All docstrings are written in **Markdown**, compatible with **pdoc**.
"""


import mido
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import os
import json


# Global state flags used by the routing engine.
# - running: whether the router loop is active
# - router_thread: background thread running the router


running = False
router_thread = None

# ---------------- Paths for presets/setlists ----------------
SONG_CONFIG_PATH = os.path.join(os.getcwd(), "midimodifier_songs.json")

"""
Path to the JSON file storing song presets and setlists.

The file structure is:

{
    "songs": {
        "Song Name": { ... preset data ... }
    },
    "setlists": {
        "Setlist Name": ["Song A", "Song B", ...]
    }
}

This file is created automatically if missing.
"""


# ---------------- UI AUTO-DETECT ----------------
def ui_scale(root):
    """
    # UI Scale

    Automatically adjusts font sizes, padding, and monitor height based on
    the detected screen width. This allows the GUI to adapt to small
    Raspberry Pi touchscreens (e.g., 480×320) or larger desktop displays.

    Parameters
    ----------
    root : tkinter.Tk  
        The root window used to query screen dimensions.

    Returns
    -------
    dict  
        A dictionary containing:
        - `font`: default font tuple  
        - `padx`: horizontal padding  
        - `pady`: vertical padding  
        - `monitor_height`: number of lines for scrolled text widgets

    Notes
    -----
    - Screens ≤ 600px wide use compact UI settings.
    - Larger screens use more spacious layout values.
    """


    w = root.winfo_screenwidth()
    if w <= 600:
        return {
            "font": ("TkDefaultFont", 10),
            "padx": 6,
            "pady": 4,
            "monitor_height": 3,
        }
    else:
        return {
            "font": ("TkDefaultFont", 12),
            "padx": 10,
            "pady": 6,
            "monitor_height": 4,
        }

# ---------------- Transpose Map ----------------
# Dictionary mapping human‑readable transposition labels to semitone offsets.
#
# Used by the Routing tab to transpose lower/upper zones independently.
#
# Examples
# --------
# "+ 1 octave" → 12  
# "- 2 semitones" → -2  
# "0" → 0
#
# The keys are displayed in scrollable dropdown menus.

transpose_map = {
    "+ 2 octaves": 24, "+ 1 octave": 12, "+ 11 semitones": 11, "+ 10 semitones": 10,
    "+ 9 semitones": 9, "+ 8 semitones": 8, "+ 7 semitones": 7, "+ 6 semitones": 6,
    "+ 5 semitones": 5, "+ 4 semitones": 4, "+ 3 semitones": 3, "+ 2 semitones": 2,
    "+ 1 semitone": 1, "0": 0, "- 1 semitone": -1, "- 2 semitones": -2,
    "- 3 semitones": -3, "- 4 semitones": -4, "- 5 semitones": -5, "- 6 semitones": -6,
    "- 7 semitones": -7, "- 8 semitones": -8, "- 9 semitones": -9, "- 10 semitones": -10,
    "- 11 semitones": -11, "- 1 octave": -12, "- 2 octaves": -24,
}

transpose_options = list(transpose_map.keys())


# ---------------- Scrollable Dropdown ----------------
def create_scrollable_dropdown(parent, variable, options):

    """
    # Scrollable Dropdown Widget

    Creates a custom dropdown widget using a `ttk.Button` that opens a
    borderless `Toplevel` window containing a scrollable `Listbox`. This
    is used instead of a standard `OptionMenu` when the number of options
    is large (e.g., transpose values, instrument lists).

    Parameters
    ----------
    parent : tkinter widget  
        The parent widget for the dropdown button.
    variable : tkinter.StringVar  
        The variable that stores the selected value.
    options : list[str]  
        A list of strings to display in the dropdown.

    Returns
    -------
    ttk.Button  
        A button that opens the scrollable dropdown when pressed.

    Notes
    -----
    - The dropdown window is borderless and positioned directly below the
      button.
    - The Listbox supports scrolling via a vertical scrollbar.
    - Clicking an item sets the associated variable and closes the window.
    - Focus‑out events automatically close the dropdown.
    """
    btn = ttk.Button(parent, textvariable=variable, width=18)

    def open_dropdown():
        top = tk.Toplevel(parent)
        top.wm_overrideredirect(True)

        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        top.geometry(f"+{x}+{y}")

        frame = ttk.Frame(top, borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(frame, height=10, activestyle="none")
        listbox.pack(side="left", fill="both", expand=True)

        for item in options:
            listbox.insert(tk.END, item)

        listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=listbox.yview)

        def select_item(event):
            if not listbox.curselection():
                return
            selection = listbox.get(listbox.curselection())
            variable.set(selection)
            top.destroy()

        listbox.bind("<ButtonRelease-1>", select_item)

        def close_on_focus_out(event):
            if not top.focus_displayof():
                top.destroy()

        top.bind("<FocusOut>", close_on_focus_out)
        top.focus_set()

    btn.config(command=open_dropdown)
    return btn

# ---------------- Panic ----------------
def panic():
    """
    # Panic — Send All Notes Off / Reset Controllers

    Sends a set of MIDI "panic" messages to all selected output ports to
    immediately silence stuck notes or runaway sustain. This function
    sends the following Control Change messages on **all 16 MIDI channels**:

    - **CC123** — All Notes Off  
    - **CC64** — Sustain Off  
    - **CC121** — Reset All Controllers  

    Output ports are determined from:
    - `lower_output_port_var`
    - `upper_output_port_var`

    Returns
    -------
    None

    Notes
    -----
    - Ports are opened temporarily using `mido.open_output()` inside a
      context manager.
    - Any port that fails to open is silently skipped.
    - The GUI status line (`router_status_var`) is updated to indicate
      that a panic was sent.
    """

    ports = set()
    lo = lower_output_port_var.get().strip()
    up = upper_output_port_var.get().strip()
    if lo:
        ports.add(lo)
    if up:
        ports.add(up)

    router_status_var.set("Panic sent.")

    for name in ports:
        try:
            with mido.open_output(name) as p:
                for ch in range(16):
                    p.send(mido.Message('control_change', channel=ch, control=123, value=0))
                    p.send(mido.Message('control_change', channel=ch, control=64, value=0))
                    p.send(mido.Message('control_change', channel=ch, control=121, value=0))
        except:
            pass

# ---------------- Router Control ----------------
def start_router():
    """
    # Start Router

    Starts the MIDI routing engine in a background thread. This function:

    1. Checks whether the router is already running.
    2. Sets the global `running` flag to `True`.
    3. Updates the GUI status (`router_status_var`).
    4. Creates and starts a daemon thread running `router_loop()`.

    Returns
    -------
    None

    Notes
    -----
    - The routing loop runs continuously until `stop_router()` sets
      `running = False`.
    - The thread is marked as a daemon so it will not block application
      shutdown.
    """

    global running, router_thread
    if running:
        return
    running = True
    router_status_var.set("Router started.")
    router_thread = threading.Thread(target=router_loop, daemon=True)
    router_thread.start()

def stop_router():
    """
    # Stop Router

    Stops the MIDI routing engine by setting the global `running` flag to
    `False`. The active routing thread will exit naturally once the flag
    is cleared.

    Returns
    -------
    None

    Notes
    -----
    - This does not close MIDI ports; the routing loop handles cleanup
      when it exits.
    - The GUI status (`router_status_var`) is updated to reflect that the
      router has stopped.
    """

    global running
    running = False
    router_status_var.set("Router stopped.")

# ---------------- Routing Loop ----------------
def router_loop():
    """
    # Router Loop — Main MIDI Processing Engine

    The core MIDI routing engine. Runs continuously in a background thread
    while `running` is `True`. This function:

    1. Opens the selected input and output ports.
    2. Reads pending MIDI messages using `iter_pending()`.
    3. Applies split‑point logic to determine lower/upper zone routing.
    4. Applies transposition per zone.
    5. Applies optional channel remapping.
    6. Sends the transformed message to the appropriate output port.
    7. Updates GUI monitors and status labels for both zones.

    Routing Rules
    -------------
    - Messages of type `note_on` and `note_off` are split based on
      `split_var.get()`:
        - `msg.note <= split_point` → **Lower Zone**
        - `msg.note > split_point` → **Upper Zone**
    - Each zone has:
        - Independent transpose (`lower_transpose_var`, `upper_transpose_var`)
        - Independent output port (`lower_output_port_var`, `upper_output_port_var`)
        - Independent channel override (`lower_zone_var`, `upper_zone_var`)
    - Non‑note messages are broadcast to **both** output ports if present.

    GUI Integration
    ---------------
    - Lower zone messages are appended to `lower_output_monitor`.
    - Upper zone messages are appended to `upper_output_monitor`.
    - Status labels (`lower_status_var`, `upper_status_var`) show:
        - Incoming note
        - Outgoing note
        - Channel
        - Split point

    Returns
    -------
    None

    Notes
    -----
    - Ports are opened once at the start of the loop.
    - The loop exits automatically when `running` becomes `False`.
    - All GUI updates are performed from the routing thread; Tkinter
      tolerates this because updates are simple text insertions.
    """

    selected_input = input_port_var.get().strip()
    selected_lower_output = lower_output_port_var.get().strip()
    selected_upper_output = upper_output_port_var.get().strip()

    inport = mido.open_input(selected_input) if selected_input else None
    out_lower = mido.open_output(selected_lower_output) if selected_lower_output else None
    out_upper = mido.open_output(selected_upper_output) if selected_upper_output else None

    while running:
        if inport:
            for msg in inport.iter_pending():

                original = msg.copy()
                split_point = split_var.get()

                if msg.type in ("note_on", "note_off"):

                    if msg.note <= split_point:
                        is_lower = True
                        out_port = out_lower
                        transpose_amount = transpose_map.get(lower_transpose_var.get(), 0)
                        out_channel = lower_zone_var.get()
                    else:
                        is_lower = False
                        out_port = out_upper
                        transpose_amount = transpose_map.get(upper_transpose_var.get(), 0)
                        out_channel = upper_zone_var.get()

                    msg.note = max(0, min(127, msg.note + transpose_amount))

                    if out_channel != "Unchanged":
                        msg.channel = int(out_channel) - 1

                    if is_lower:
                        if out_port:
                            out_port.send(msg)
                        lower_output_monitor.insert(tk.END, str(msg) + "\n")
                        lower_output_monitor.see(tk.END)
                        lower_status_var.set(
                            f"IN: {original.type} {original.note} ch{original.channel+1}   "
                            f"OUT: {msg.type} {msg.note}   Split: {split_point}"
                        )
                    else:
                        if out_port:
                            out_port.send(msg)
                        upper_output_monitor.insert(tk.END, str(msg) + "\n")
                        upper_output_monitor.see(tk.END)
                        upper_status_var.set(
                            f"IN: {original.type} {original.note} ch{original.channel+1}   "
                            f"OUT: {msg.type} {msg.note}   Split: {split_point}"
                        )

                else:
                    if out_lower:
                        out_lower.send(msg)
                    if out_upper:
                        out_upper.send(msg)

# ---------------- Instrument Definitions (separate lower/upper) ----------------
lower_instrument_file_var = None
upper_instrument_file_var = None

lower_instrument_dict = {}
upper_instrument_dict = {}

lower_instrument_names = []
upper_instrument_names = []

def load_lower_instrument_definition(filename):
    """
    # Load Lower Instrument Definition

    Loads a General MIDI instrument definition file (JSON) for the **lower
    zone**. The JSON file maps program numbers to instrument names:

    ```json
    {
        "0": "Acoustic Grand Piano",
        "1": "Bright Piano",
        ...
    }
    ```

    This function:

    1. Reads the JSON file from the current working directory.
    2. Populates `lower_instrument_dict` with program→name mappings.
    3. Builds `lower_instrument_names` as `"num - name"` strings.
    4. Updates the GUI variable `lower_instrument_file_var`.
    5. Rebuilds the lower program dropdown menu.

    Parameters
    ----------
    filename : str  
        Name of the `.gm.json` file to load.

    Returns
    -------
    None

    Notes
    -----
    - Errors are reported via `router_status_var`.
    - The dropdown menu is rebuilt using `rebuild_lower_program_dropdown()`.
    """

    global lower_instrument_dict, lower_instrument_names

    lower_instrument_dict = {}
    lower_instrument_names = []

    try:
        with open(os.path.join(os.getcwd(), filename), "r") as f:
            lower_instrument_dict = json.load(f)
    except Exception as e:
        router_status_var.set(f"Error loading lower instrument file: {e}")
        return

    for num_str, name in lower_instrument_dict.items():
        lower_instrument_names.append(f"{num_str} - {name}")

    lower_instrument_file_var.set(filename)
    rebuild_lower_program_dropdown()

def load_upper_instrument_definition(filename):
    """
    # Load Upper Instrument Definition

    Same behavior as `load_lower_instrument_definition()`, but for the
    **upper zone**. Loads a General MIDI instrument definition JSON file
    and updates:

    - `upper_instrument_dict`
    - `upper_instrument_names`
    - `upper_instrument_file_var`
    - The upper program dropdown menu

    Parameters
    ----------
    filename : str  
        Name of the `.gm.json` file to load.

    Returns
    -------
    None

    Notes
    -----
    - Errors are reported via `router_status_var`.
    - The dropdown menu is rebuilt using `rebuild_upper_program_dropdown()`.
    """

    global upper_instrument_dict, upper_instrument_names

    upper_instrument_dict = {}
    upper_instrument_names = []

    try:
        with open(os.path.join(os.getcwd(), filename), "r") as f:
            upper_instrument_dict = json.load(f)
    except Exception as e:
        router_status_var.set(f"Error loading upper instrument file: {e}")
        return

    for num_str, name in upper_instrument_dict.items():
        upper_instrument_names.append(f"{num_str} - {name}")

    upper_instrument_file_var.set(filename)
    rebuild_upper_program_dropdown()

def rebuild_lower_program_dropdown():
    """
    # Rebuild Lower Program Dropdown

    Reconstructs the OptionMenu for selecting lower‑zone Program Change
    values. The menu is populated using `lower_instrument_names`, which
    contains `"num - name"` strings.

    Behavior
    --------
    - Clears existing menu entries.
    - Adds each instrument name as a selectable command.
    - Sets the default selection to the first item, or `"0"` if empty.

    Returns
    -------
    None
    """

    menu = lower_program_menu["menu"]
    menu.delete(0, "end")

    for name in lower_instrument_names:
        menu.add_command(label=name, command=lambda v=name: lower_program_var.set(v))

    if lower_instrument_names:
        lower_program_var.set(lower_instrument_names[0])
    else:
        lower_program_var.set("0")

def rebuild_upper_program_dropdown():
    """
    # Rebuild Upper Program Dropdown

    Same behavior as `rebuild_lower_program_dropdown()`, but for the
    **upper zone**.

    Returns
    -------
    None
    """

    menu = upper_program_menu["menu"]
    menu.delete(0, "end")

    for name in upper_instrument_names:
        menu.add_command(label=name, command=lambda v=name: upper_program_var.set(v))

    if upper_instrument_names:
        upper_program_var.set(upper_instrument_names[0])
    else:
        upper_program_var.set("0")

def refresh_instruments():
    """
    # Refresh Instrument Definition Files

    Scans the current working directory for General MIDI instrument
    definition files matching:

    ```
    *.gm.json
    ```

    (excluding drumkit files)

    This function:

    1. Clears both lower and upper instrument file menus.
    2. Adds each `.gm.json` file to both menus.
    3. Loads the first file automatically into both zones.
    4. Rebuilds both program dropdown menus.

    Returns
    -------
    None

    Notes
    -----
    - If no GM files are found, both instrument file variables are set to
      `"No files"` and program menus are reset.
    """

    folder = os.getcwd()
    gm_files = [f for f in os.listdir(folder)
                if f.lower().endswith(".gm.json") and "drum" not in f.lower()]

    lower_instr_menu["menu"].delete(0, "end")
    upper_instr_menu["menu"].delete(0, "end")

    if not gm_files:
        lower_instrument_file_var.set("No files")
        upper_instrument_file_var.set("No files")
        rebuild_lower_program_dropdown()
        rebuild_upper_program_dropdown()
        return

    for fname in gm_files:
        lower_instr_menu["menu"].add_command(
            label=fname,
            command=lambda v=fname: load_lower_instrument_definition(v)
        )
        upper_instr_menu["menu"].add_command(
            label=fname,
            command=lambda v=fname: load_upper_instrument_definition(v)
        )

    lower_instrument_file_var.set(gm_files[0])
    upper_instrument_file_var.set(gm_files[0])

    load_lower_instrument_definition(gm_files[0])
    load_upper_instrument_definition(gm_files[0])

def get_program_number(var):
    """
    # Extract Program Number

    Parses a `"num - name"` string and returns the integer program number.

    Parameters
    ----------
    var : tkinter.StringVar  
        Variable containing a `"num - name"` formatted string.

    Returns
    -------
    int  
        The program number, or `0` if parsing fails.

    Notes
    -----
    This helper is used by Program Change and GS Bank Select functions.
    """

    try:
        return int(var.get().split(" - ")[0])
    except:
        return 0

def send_lower_program_change():
    """
    # Send Lower Program Change

    Sends a MIDI Program Change message to the lower zone’s output port.
    The program number is extracted from `lower_program_var`, and the
    channel is determined by `lower_zone_var`.

    Behavior
    --------
    - If the lower zone channel is `"Unchanged"` or no output port is
      selected, the function exits silently.
    - Opens the output port temporarily using `mido.open_output()`.
    - Sends a `program_change` message with:
        - `program = extracted program number`
        - `channel = lower_zone_var - 1`

    Returns
    -------
    None

    Notes
    -----
    - Errors opening the port are silently ignored.
    - GUI status is updated via `router_status_var`.
    """

    zone_ch = lower_zone_var.get()
    port_name = lower_output_port_var.get().strip()
    if zone_ch == "Unchanged" or not port_name:
        return

    prog = get_program_number(lower_program_var)
    try:
        port = mido.open_output(port_name)
        port.send(mido.Message('program_change', program=prog, channel=int(zone_ch)-1))
        router_status_var.set(f"Lower Program Change sent — {prog}")
    except:
        pass

def send_upper_program_change():
    """
    # Send Upper Program Change

    Same behavior as `send_lower_program_change()`, but for the **upper
    zone**.

    Returns
    -------
    None
    """

    zone_ch = upper_zone_var.get()
    port_name = upper_output_port_var.get().strip()
    if zone_ch == "Unchanged" or not port_name:
        return

    prog = get_program_number(upper_program_var)
    try:
        port = mido.open_output(port_name)
        port.send(mido.Message('program_change', program=prog, channel=int(zone_ch)-1))
        router_status_var.set(f"Upper Program Change sent — {prog}")
    except:
        pass

# ---------------- Drumkit Support ----------------

def refresh_drumkit_files():
    """
    # Refresh Drumkit Definition Files

    Scans the current working directory for drumkit definition files
    matching:

    ```
    *drumkits.gm.json
    ```

    This function:

    1. Clears the drumkit file OptionMenu.
    2. Adds each drumkit file found.
    3. Automatically loads the first drumkit file.
    4. Updates `selected_drumkit_file`.

    Returns
    -------
    None

    Notes
    -----
    - If no drumkit files are found, the GUI variable is set to
      `"No drumkit files found"`.
    """

    folder = os.getcwd()
    drumkit_file_menu["menu"].delete(0, "end")

    found = False
    for filename in os.listdir(folder):
        if filename.lower().endswith("drumkits.gm.json"):
            drumkit_file_menu["menu"].add_command(
                label=filename,
                command=lambda v=filename: (
                    selected_drumkit_file.set(v),
                    load_drumkit_file()
                )
            )
            if not found:
                selected_drumkit_file.set(filename)
                load_drumkit_file()
                found = True

    if not found:
        selected_drumkit_file.set("No drumkit files found")
        

def load_drumkit_file():
    """
    # Load Drumkit Definition File

    Loads the selected drumkit JSON file, which maps program numbers to
    drumkit names:

    ```json
    {
        "0": "Standard Kit",
        "8": "Room Kit",
        "16": "Power Kit",
        ...
    }
    ```

    This function:

    1. Reads the JSON file.
    2. Populates `drumkit_names` with `"num - name"` strings.
    3. Rebuilds the drumkit selection OptionMenu.
    4. Sets the default drumkit to the first entry.

    Returns
    -------
    None

    Notes
    -----
    - Errors are reported via `router_status_var`.
    - Drumkit definitions are used by `send_drumkit_change()`.
    """

    global drumkit_names
    drumkit_names.clear()

    filename = selected_drumkit_file.get().strip()
    if not filename:
        return

    try:
        with open(filename, "r") as f:
            data = json.load(f)
            for num_str, name in data.items():
                drumkit_names.append(f"{num_str} - {name}")
    except Exception as e:
        router_status_var.set(f"Error loading drumkits: {e}")
        return

    drumkit_menu["menu"].delete(0, "end")
    for name in drumkit_names:
        drumkit_menu["menu"].add_command(label=name, command=lambda v=name: drumkit_var.set(v))

    if drumkit_names:
        drumkit_var.set(drumkit_names[0])

def send_drumkit_change():
    """
    # Send Drumkit Program Change

    Sends a Program Change message to the selected output port using the
    drumkit definition loaded from the drumkit JSON file.

    Behavior
    --------
    - Extracts the program number from `drumkit_var`.
    - Uses the drumkit channel from `drumkit_channel_var`.
    - Opens the lower zone output port (drumkits always use lower port).
    - Sends GS‑compatible Bank Select messages when needed:
        - If the filename contains `"sc55"` or `"gs"`, sends:
            - CC0 (Bank MSB) = 0
            - CC32 (Bank LSB) = 0
    - Sends the Program Change message.

    Returns
    -------
    None

    Notes
    -----
    - Errors opening the port are reported via `router_status_var`.
    - Drumkit Program Change is independent of split‑point routing.
    """

    port_name = lower_output_port_var.get().strip()
    if not port_name:
        router_status_var.set("No output port selected.")
        return

    try:
        port = mido.open_output(port_name)
    except:
        router_status_var.set("Could not open output port.")
        return

    try:
        prog = int(drumkit_var.get().split(" - ")[0])
    except:
        prog = 0

    ch = drumkit_channel_var.get() - 1

    filename = selected_drumkit_file.get().lower()

    if "sc55" in filename or "gs" in filename:
        port.send(mido.Message('control_change', channel=ch, control=0, value=0))
        port.send(mido.Message('control_change', channel=ch, control=32, value=0))

    port.send(mido.Message('program_change', channel=ch, program=prog))

    router_status_var.set(f"Drumkit Change sent — Ch {ch+1}, Prog {prog}")

# ---------------- GS Support ----------------
def send_gs_bank_and_program(lower=True):
    """
    # Send GS Bank Select + Program Change

    Sends a Roland GS‑compatible Bank Select (MSB/LSB) followed by a
    Program Change message to either the **lower** or **upper** zone’s
    output port.

    GS Bank Select uses:
    - **CC0**  → Bank MSB  
    - **CC32** → Bank LSB  

    This function:

    1. Determines whether the lower or upper zone is being targeted.
    2. Reads the zone’s:
        - Output port
        - Channel
        - Bank MSB (CC0)
        - Bank LSB (CC32)
        - Program number (from GM instrument definition)
    3. Opens the output port.
    4. Sends:
        - `control_change` CC0 (Bank MSB)
        - `control_change` CC32 (Bank LSB)
        - `program_change` with the selected program number

    Parameters
    ----------
    lower : bool, default=True  
        If `True`, sends to the lower zone.  
        If `False`, sends to the upper zone.

    Returns
    -------
    None

    Notes
    -----
    - If the zone channel is `"Unchanged"` or no output port is selected,
      the function exits silently.
    - Errors opening the port are silently ignored.
    - The GUI status (`router_status_var`) is updated with the bank and
      program sent.
    - This function is used in the **GS Bank/Reset** tab.
    """

    if lower:
        zone_ch = lower_zone_var.get()
        port_name = lower_output_port_var.get().strip()
        bank_msb = lower_bank_msb_var.get()
        bank_lsb = lower_bank_lsb_var.get()
        program = get_program_number(lower_program_var)
    else:
        zone_ch = upper_zone_var.get()
        port_name = upper_output_port_var.get().strip()
        bank_msb = upper_bank_msb_var.get()
        bank_lsb = upper_bank_lsb_var.get()
        program = get_program_number(upper_program_var)

    if zone_ch == "Unchanged" or not port_name:
        return

    try:
        port = mido.open_output(port_name)
    except:
        return

    ch = int(zone_ch) - 1

    port.send(mido.Message('control_change', channel=ch, control=0, value=bank_msb))
    port.send(mido.Message('control_change', channel=ch, control=32, value=bank_lsb))
    port.send(mido.Message('program_change', channel=ch, program=program))

    router_status_var.set(
        f"GS Bank+Program sent — {'Lower' if lower else 'Upper'}: "
        f"Bank {bank_msb}:{bank_lsb} Prog {program}"
    )

def send_gs_reset():
    """
    # Send GS Reset (Roland GS SysEx)

    Sends a Roland GS Reset SysEx message to all selected output ports.
    This resets GS‑compatible devices (e.g., Roland SC‑55, SC‑88) to their
    default state.

    The GS Reset SysEx message is:

    ```
    F0 41 10 42 12 40 00 7F 00 41 F7
    ```

    In your script, the SysEx payload is:

    ```python
    [0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41]
    ```

    This function:

    1. Collects all selected output ports:
        - `lower_output_port_var`
        - `upper_output_port_var`
    2. Opens each port.
    3. Sends the GS Reset SysEx message.

    Returns
    -------
    None

    Notes
    -----
    - Ports that fail to open are silently skipped.
    - The GUI status (`router_status_var`) is updated to indicate that the
      GS Reset was sent.
    - GS Reset is useful when switching between presets or setlists that
      use different GS banks.
    """

    ports = set()
    lo = lower_output_port_var.get().strip()
    up = upper_output_port_var.get().strip()
    if lo:
        ports.add(lo)
    if up:
        ports.add(up)

    gs_reset = mido.Message('sysex', data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41])

    for name in ports:
        try:
            with mido.open_output(name) as p:
                p.send(gs_reset)
        except:
            pass

    router_status_var.set("GS Reset sent to available output ports.")

# ---------------- Song Presets / Setlists JSON ----------------
song_cfg = {
    "songs": {},
    "setlists": {}
}
current_setlist_name = ""
current_setlist_index = 0

def load_song_config():
    """
    # Load Song Configuration (Presets + Setlists)

    Loads the JSON configuration file defined by `SONG_CONFIG_PATH`.
    The file contains two top‑level dictionaries:

    ```json
    {
        "songs": {
            "Song Name": { ... preset data ... }
        },
        "setlists": {
            "Setlist Name": ["Song A", "Song B", ...]
        }
    }
    ```

    Behavior
    --------
    - If the file does not exist, initializes an empty configuration.
    - If the file exists but cannot be parsed, falls back to an empty
      configuration.

    Returns
    -------
    None

    Notes
    -----
    - This function is called during GUI initialization.
    - The global `song_cfg` dictionary is updated.
    """

    global song_cfg
    if not os.path.exists(SONG_CONFIG_PATH):
        song_cfg = {"songs": {}, "setlists": {}}
        return
    try:
        with open(SONG_CONFIG_PATH, "r") as f:
            song_cfg = json.load(f)
    except:
        song_cfg = {"songs": {}, "setlists": {}}

def save_song_config():
    """
    # Save Song Configuration

    Writes the global `song_cfg` dictionary to `SONG_CONFIG_PATH` using
    pretty‑printed JSON formatting.

    Returns
    -------
    None

    Notes
    -----
    - Errors during saving are silently ignored.
    - Called after saving or deleting presets and setlists.
    """

    try:
        with open(SONG_CONFIG_PATH, "w") as f:
            json.dump(song_cfg, f, indent=4)
    except:
        pass

def save_song_preset():
    """
    # Save Song Preset

    Saves the current routing configuration as a named preset. The preset
    includes:

    - Split point  
    - Lower/upper zone channels  
    - Lower/upper transpose  
    - Input/output ports  
    - Instrument definition files  
    - Program numbers  
    - GS bank MSB/LSB  
    - Drumkit file, drumkit selection, drumkit channel  

    Behavior
    --------
    1. Reads the song name from `song_name_var`.
    2. Validates that a name is provided.
    3. Stores all relevant Tkinter variable values into `song_cfg["songs"]`.
    4. Saves the updated configuration to disk.
    5. Refreshes the song list dropdown.
    6. Updates the GUI status.

    Returns
    -------
    None

    Notes
    -----
    - Presets allow instant recall of complex routing setups.
    - Presets are independent of setlists.
    """

    name = song_name_var.get().strip()
    if not name:
        router_status_var.set("Enter a song name.")
        return

    song_cfg.setdefault("songs", {})
    song_cfg["songs"][name] = {
        "split_point": split_var.get(),
        "lower_zone": lower_zone_var.get(),
        "upper_zone": upper_zone_var.get(),
        "lower_transpose": lower_transpose_var.get(),
        "upper_transpose": upper_transpose_var.get(),
        "input_port": input_port_var.get(),
        "lower_output_port": lower_output_port_var.get(),
        "upper_output_port": upper_output_port_var.get(),
        "lower_instr_file": lower_instrument_file_var.get(),
        "upper_instr_file": upper_instrument_file_var.get(),
        "lower_program": lower_program_var.get(),
        "upper_program": upper_program_var.get(),
        "lower_bank_msb": lower_bank_msb_var.get(),
        "lower_bank_lsb": lower_bank_lsb_var.get(),
        "upper_bank_msb": upper_bank_msb_var.get(),
        "upper_bank_lsb": upper_bank_lsb_var.get(),
        "drumkit_file": selected_drumkit_file.get(),
        "drumkit": drumkit_var.get(),
        "drumkit_channel": drumkit_channel_var.get()
    }
    save_song_config()
    refresh_song_list()
    router_status_var.set(f"Saved preset for '{name}'")

def load_song_preset(name):
    """
    # Load Song Preset

    Loads a previously saved preset by name and applies all stored
    settings to the GUI and routing variables.

    Loaded fields include:
    - Split point  
    - Zone channels  
    - Transpose values  
    - Input/output ports  
    - Instrument definition files  
    - Program numbers  
    - GS bank MSB/LSB  
    - Drumkit file, drumkit selection, drumkit channel  

    Parameters
    ----------
    name : str  
        The name of the preset to load.

    Returns
    -------
    None

    Notes
    -----
    - Instrument and drumkit files are loaded immediately.
    - GUI status is updated to reflect the loaded preset.
    - If the preset does not exist, a status message is shown.
    """

    songs = song_cfg.get("songs", {})
    if name not in songs:
        router_status_var.set(f"No preset found for '{name}'")
        return

    preset = songs[name]

    split_var.set(preset.get("split_point", 60))
    lower_zone_var.set(preset.get("lower_zone", "Unchanged"))
    upper_zone_var.set(preset.get("upper_zone", "Unchanged"))
    lower_transpose_var.set(preset.get("lower_transpose", "0"))
    upper_transpose_var.set(preset.get("upper_transpose", "0"))
    input_port_var.set(preset.get("input_port", ""))
    lower_output_port_var.set(preset.get("lower_output_port", ""))
    upper_output_port_var.set(preset.get("upper_output_port", ""))

    lf = preset.get("lower_instr_file", "")
    uf = preset.get("upper_instr_file", "")
    if lf:
        load_lower_instrument_definition(lf)
    if uf:
        load_upper_instrument_definition(uf)

    lower_program_var.set(preset.get("lower_program", "0"))
    upper_program_var.set(preset.get("upper_program", "0"))

    lower_bank_msb_var.set(preset.get("lower_bank_msb", 0))
    lower_bank_lsb_var.set(preset.get("lower_bank_lsb", 0))
    upper_bank_msb_var.set(preset.get("upper_bank_msb", 0))
    upper_bank_lsb_var.set(preset.get("upper_bank_lsb", 0))

    df = preset.get("drumkit_file", "")
    if df:
        selected_drumkit_file.set(df)
        load_drumkit_file()
    drumkit_var.set(preset.get("drumkit", drumkit_var.get()))
    drumkit_channel_var.set(preset.get("drumkit_channel", 10))

    router_status_var.set(f"Loaded preset for '{name}'")

def refresh_song_list():
    """
    # Refresh Song List

    Updates the song selection dropdown (`song_combo`) with all saved
    preset names sorted alphabetically.

    Returns
    -------
    None

    Notes
    -----
    - Called after loading configuration and after saving/deleting presets.
    """

    songs = sorted(song_cfg.get("songs", {}).keys())
    song_combo["values"] = songs

def delete_song_preset():
    """
    # Delete Song Preset

    Deletes a preset by name from `song_cfg["songs"]`.

    Behavior
    --------
    - Reads the name from `song_name_var`.
    - Validates that the name exists.
    - Removes the preset.
    - Saves the updated configuration.
    - Refreshes the song list.
    - Updates GUI status.

    Returns
    -------
    None

    Notes
    -----
    - If the preset does not exist, a status message is shown.
    """

    name = song_name_var.get().strip()
    if not name:
        router_status_var.set("Enter a song name to delete.")
        return
    if name in song_cfg.get("songs", {}):
        del song_cfg["songs"][name]
        save_song_config()
        refresh_song_list()
        router_status_var.set(f"Deleted song '{name}'")
    else:
        router_status_var.set(f"No preset found for '{name}'")

def load_selected_song_preset():
    """
    # Load Selected Song Preset

    Loads the preset currently selected in the song dropdown (`song_combo`)
    and updates `song_name_var` accordingly.

    Returns
    -------
    None

    Notes
    -----
    - If no song is selected, a status message is shown.
    """

    name = song_combo.get().strip()
    if not name:
        router_status_var.set("Select a song to load.")
        return
    song_name_var.set(name)
    load_song_preset(name)

def refresh_setlist_list():
    """
    # Refresh Setlist List

    Updates the setlist dropdown (`setlist_combo`) with all saved setlist
    names sorted alphabetically.

    Returns
    -------
    None

    Notes
    -----
    - Called after loading configuration and after saving/deleting setlists.
    """

    setlists = sorted(song_cfg.get("setlists", {}).keys())
    setlist_combo["values"] = setlists

def create_update_setlist():
    """
    # Create or Update Setlist

    Creates a new setlist or updates an existing one. A setlist is a
    comma‑separated list of song names entered into the text editor
    (`setlist_songs_text`).

    Behavior
    --------
    1. Reads the setlist name from `setlist_name_var`.
    2. Reads the comma‑separated song list.
    3. Validates that at least one song name is provided.
    4. Stores the list in `song_cfg["setlists"]`.
    5. Saves the configuration.
    6. Refreshes the setlist dropdown.
    7. Updates GUI status.

    Returns
    -------
    None

    Notes
    -----
    - Song names must match existing presets to be useful.
    - Setlists allow rapid switching between songs during performance.
    """

    name = setlist_name_var.get().strip()
    if not name:
        router_status_var.set("Enter a setlist name.")
        return

    raw = setlist_songs_text.get("1.0", "end").strip()
    if not raw:
        router_status_var.set("Enter song names (comma-separated).")
        return

    songs = [s.strip() for s in raw.split(",") if s.strip()]
    if not songs:
        router_status_var.set("No valid song names found.")
        return

    song_cfg.setdefault("setlists", {})
    song_cfg["setlists"][name] = songs
    save_song_config()
    refresh_setlist_list()
    router_status_var.set(f"Setlist '{name}' saved with {len(songs)} songs")

def delete_setlist():
    """
    # Delete Setlist

    Deletes a setlist by name from `song_cfg["setlists"]`.

    Behavior
    --------
    - Reads the name from `setlist_name_var`.
    - Validates that the name exists.
    - Removes the setlist.
    - Saves the updated configuration.
    - Refreshes the setlist dropdown.
    - Updates GUI status.

    Returns
    -------
    None

    Notes
    -----
    - If the setlist does not exist, a status message is shown.
    """

    name = setlist_name_var.get().strip()
    if not name:
        router_status_var.set("Enter a setlist name to delete.")
        return

    if name in song_cfg.get("setlists", {}):
        del song_cfg["setlists"][name]
        save_song_config()
        refresh_setlist_list()
        router_status_var.set(f"Deleted setlist '{name}'")
    else:
        router_status_var.set(f"No setlist found for '{name}'")

def start_setlist():
    """
    # Start Setlist Playback

    Begins playback of a setlist by loading the first song in the list.
    This function:

    1. Reads the selected setlist name.
    2. Validates that the setlist exists and contains songs.
    3. Sets `current_setlist_name` and resets `current_setlist_index`.
    4. Loads the first song preset.
    5. Updates GUI status.

    Returns
    -------
    None

    Notes
    -----
    - The setlist editor is updated to show the full song list.
    - This function prepares the system for `next_song_in_setlist()`.
    """

    global current_setlist_name, current_setlist_index
    name = setlist_combo.get().strip()
    if not name:
        router_status_var.set("Select a setlist to start.")
        return

    setlists = song_cfg.get("setlists", {})
    songs = setlists.get(name, [])
    if not songs:
        router_status_var.set(f"Setlist '{name}' is empty.")
        return

    current_setlist_name = name
    current_setlist_index = 0
    first_song = songs[current_setlist_index]
    song_name_var.set(first_song)
    load_song_preset(first_song)
    router_status_var.set(f"Setlist '{name}' started – now '{first_song}'")

def next_song_in_setlist():
    """
    # Load Next Song in Setlist

    Advances to the next song in the active setlist and loads its preset.

    Behavior
    --------
    - Validates that a setlist is active.
    - Increments `current_setlist_index`.
    - Loads the next song preset.
    - Updates GUI status.
    - Updates the setlist editor with the full song list.

    Returns
    -------
    None

    Notes
    -----
    - If the end of the setlist is reached, a status message is shown.
    - The index does not wrap; it stops at the final song.
    """

    global current_setlist_name, current_setlist_index
    name = current_setlist_name
    if not name:
        router_status_var.set("No active setlist.")
        return

    setlists = song_cfg.get("setlists", {})
    songs = setlists.get(name, [])
    if not songs:
        router_status_var.set(f"Setlist '{name}' is empty.")
        return

    current_setlist_index += 1
    if current_setlist_index >= len(songs):
        router_status_var.set(f"End of setlist '{name}'")
        current_setlist_index = len(songs) - 1
        return

    next_song = songs[current_setlist_index]
    song_name_var.set(next_song)
    load_song_preset(next_song)
    router_status_var.set(f"Setlist '{name}' – next '{next_song}'")

    setlist_songs_text.delete("1.0", "end")
    setlist_songs_text.insert("1.0", ", ".join(songs))

# ---------------- GUI SETUP ----------------

# GUI Initialization
# 
# Initializes the main Tkinter window and configures the multi‑tab interface.
# The GUI is optimized for Raspberry Pi touchscreens (480×320) using:
#
# - Scaled fonts (via `ui_scale()`)
# - Compact padding
# - Large buttons
# - High‑contrast layout
#
# Tabs included:
# 1. Routing
# 2. MIDI Ports
# 3. Program Change
# 4. Drumkits
# 5. GS Bank/Reset
# 6. Song Presets
# 7. Setlists
#
# The GUI uses Tkinter variables (`StringVar`, `IntVar`) to store all routing
# parameters, instrument selections, drumkit settings, and preset metadata.

# Full GUI Construction
# 
# Builds the complete multi‑tab Tkinter interface used by MidiModifier.
# The GUI includes seven tabs:
#
# 1. **Routing** — split point, transpose, channels, monitoring, panic, start/stop  
# 2. **MIDI Ports** — input/output port selection and refresh  
# 3. **Program Change** — GM instrument files, program selection, program change  
# 4. **Drumkits** — drumkit definition files, drumkit selection, drumkit change  
# 5. **GS Bank/Reset** — GS Bank Select (MSB/LSB), GS Program Change, GS Reset SysEx  
# 6. **Song Presets** — save/load/delete presets  
# 7. **Setlists** — create/update/delete setlists, start/next song  
#
# The GUI uses Tkinter variables (`StringVar`, `IntVar`) to store all routing
# parameters, instrument selections, drumkit settings, GS bank values, and
# preset metadata.

# Notes
# -----
# - Layout is optimized for Raspberry Pi touchscreens using `ui_scale()`.
# - ScrolledText widgets provide real‑time MIDI monitoring.
# - OptionMenus and custom scrollable dropdowns provide compact selection
#   interfaces for large lists (transpose values, GM instruments, drumkits).
# - All routing logic is driven by GUI variable values.

root = tk.Tk()
root.title("MIDI Router with Monitoring")

ui = ui_scale(root)
root.option_add("*Font", ui["font"])

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

# ---------------- Tk Variables ----------------
split_var = tk.IntVar(value=60)
router_status_var = tk.StringVar(value="Idle.")

lower_transpose_var = tk.StringVar(value="0")
upper_transpose_var = tk.StringVar(value="0")

zone_options = ["Unchanged"] + [str(i) for i in range(1, 17)]
lower_zone_var = tk.StringVar(value="Unchanged")
upper_zone_var = tk.StringVar(value="Unchanged")

lower_output_var = tk.StringVar(value="Output Channel: (incoming)")
upper_output_var = tk.StringVar(value="Output Channel: (incoming)")

lower_output_port_var = tk.StringVar(value="")
upper_output_port_var = tk.StringVar(value="")

input_port_var = tk.StringVar(value="")

lower_status_var = tk.StringVar(value="Lower zone idle.")
upper_status_var = tk.StringVar(value="Upper zone idle.")

lower_bank_msb_var = tk.IntVar(value=0)
lower_bank_lsb_var = tk.IntVar(value=0)
upper_bank_msb_var = tk.IntVar(value=0)
upper_bank_lsb_var = tk.IntVar(value=0)

selected_drumkit_file = tk.StringVar(value="")
drumkit_var = tk.StringVar(value="")
drumkit_names = []
drumkit_channel_var = tk.IntVar(value=10)

lower_instrument_file_var = tk.StringVar(value="")
upper_instrument_file_var = tk.StringVar(value="")

# Preset / setlist vars
song_name_var = tk.StringVar(value="")
setlist_name_var = tk.StringVar(value="")

# ---------------- Routing Tab ----------------
# Routing Tab

# The main performance tab. Provides real‑time control over:
#
# - Split point (0–127)
# - Lower/upper zone MIDI channels
# - Lower/upper transpose values
# - Lower/upper output ports
# - Start/Stop router controls
# - Panic button
# - Real‑time MIDI monitoring for both zones
# - Status lines showing incoming/outgoing note, channel, and split point
# 
# Widgets include:
# - Scrollable dropdowns for transpose selection
# - Spinbox for split point
# - OptionMenus for channel selection
# - ScrolledText widgets for monitoring routed MIDI messages
# - Status labels for lower/upper zones
# - Start/Stop buttons controlling the routing thread
#
# This tab is the primary interface used during live performance.

tab = ttk.Frame(notebook, padding=ui["padx"])
notebook.add(tab, text="Routing")

panic_button = ttk.Button(tab, text="Panic", command=panic)
panic_button.grid(row=0, column=1, pady=(0, ui["pady"]))

ttk.Label(tab, text="Transpose Lower Zone:").grid(row=1, column=0, sticky="w", padx=(10, 5))
lower_transpose_dropdown = create_scrollable_dropdown(tab, lower_transpose_var, transpose_options)
lower_transpose_dropdown.grid(row=2, column=0, sticky="w", padx=(10, 5))

ttk.Label(tab, text="Transpose Upper Zone:").grid(row=1, column=2, sticky="e", padx=(5, 10))
upper_transpose_dropdown = create_scrollable_dropdown(tab, upper_transpose_var, transpose_options)
upper_transpose_dropdown.grid(row=2, column=2, sticky="e", padx=(5, 10))

ttk.Label(tab, text="Lower Zone Channel:").grid(row=3, column=0, sticky="w", padx=(10, 5))
ttk.Label(tab, text="Split Point (0–127):").grid(row=3, column=1)
ttk.Label(tab, text="Upper Zone Channel:").grid(row=3, column=2, sticky="e", padx=(5, 10))

ttk.OptionMenu(tab, lower_zone_var, "Unchanged", *zone_options).grid(row=4, column=0, sticky="w", padx=(10, 5))

split_spin = tk.Spinbox(tab, from_=0, to=127, textvariable=split_var, width=5)
split_spin.grid(row=4, column=1, pady=ui["pady"])

ttk.OptionMenu(tab, upper_zone_var, "Unchanged", *zone_options).grid(row=4, column=2, sticky="e", padx=(5, 10))

startstop_frame = ttk.Frame(tab)
startstop_frame.grid(row=5, column=1)

start_button = ttk.Button(startstop_frame, text="Start", command=start_router)
stop_button = ttk.Button(startstop_frame, text="Stop", command=stop_router)

start_button.pack(side="left", padx=(0, 10))
stop_button.pack(side="right", padx=(10, 0))

ttk.Label(tab, textvariable=lower_output_var).grid(row=6, column=0, sticky="w", padx=(10, 5))
ttk.Label(tab, textvariable=upper_output_var).grid(row=6, column=2, sticky="e", padx=(5, 10))

ttk.Label(tab, text="Lower Zone Output Port:").grid(row=7, column=0, sticky="w", padx=(10, 5))
ttk.Label(tab, text="Upper Zone Output Port:").grid(row=7, column=2, sticky="e", padx=(5, 10))

lower_output_port_menu = ttk.OptionMenu(tab, lower_output_port_var, "")
upper_output_port_menu = ttk.OptionMenu(tab, upper_output_port_var, "")

lower_output_port_menu.grid(row=8, column=0, sticky="ew", padx=(10, 5))
upper_output_port_menu.grid(row=8, column=2, sticky="ew", padx=(5, 10))

ttk.Label(tab, text="Lower Zone Output:").grid(row=9, column=0, sticky="w", padx=(10, 5))
lower_output_monitor = scrolledtext.ScrolledText(tab, width=30, height=ui["monitor_height"])
lower_output_monitor.grid(row=10, column=0, sticky="nsew", padx=(10, 5))

ttk.Label(tab, text="Lower Zone Status:").grid(row=11, column=0, sticky="w", padx=(10, 5))
ttk.Label(tab, textvariable=lower_status_var, relief="sunken", anchor="w").grid(
    row=12, column=0, sticky="ew", padx=(10, 5), pady=(0, 5)
)

ttk.Label(tab, text="Upper Zone Output:").grid(row=9, column=2, sticky="e", padx=(5, 10))
upper_output_monitor = scrolledtext.ScrolledText(tab, width=30, height=ui["monitor_height"])
upper_output_monitor.grid(row=10, column=2, sticky="nsew", padx=(5, 10))

ttk.Label(tab, text="Upper Zone Status:").grid(row=11, column=2, sticky="e", padx=(5, 10))
ttk.Label(tab, textvariable=upper_status_var, relief="sunken", anchor="w").grid(
    row=12, column=2, sticky="ew", padx=(5, 10), pady=(0, 5)
)

status_frame = ttk.Frame(tab)
status_frame.grid(row=13, column=0, columnspan=3, pady=(10, 0))
status_label = ttk.Label(status_frame, textvariable=router_status_var, relief="sunken", anchor="center", width=40)
status_label.pack()

tab.rowconfigure(10, weight=1)
tab.columnconfigure(0, weight=1)
tab.columnconfigure(1, weight=0)
tab.columnconfigure(2, weight=1)

# ---------------- MIDI Ports Tab ----------------
# MIDI Ports Tab
#
# Provides selection and refreshing of available MIDI input/output ports.
#
# Features:
# - Dropdown for selecting the active MIDI input port
# - Dropdowns for selecting lower/upper output ports
# - "Refresh Ports" button that rescans the system using `mido.get_input_names()`
#   and `mido.get_output_names()`

# Notes
# -----
# - Ports are displayed using OptionMenus.
# - Refreshing ports updates all three dropdowns.
# - The selected ports are used by the routing engine.

tab_ports = ttk.Frame(notebook, padding=ui["padx"])
notebook.add(tab_ports, text="MIDI Ports")

ttk.Label(tab_ports, text="Input Port:").grid(row=0, column=0, sticky="w")
input_menu = ttk.OptionMenu(tab_ports, input_port_var, "")
input_menu.grid(row=0, column=1, sticky="ew")

def refresh_ports():
    inputs = mido.get_input_names()
    outputs = mido.get_output_names()

    input_menu["menu"].delete(0, "end")
    for p in inputs:
        input_menu["menu"].add_command(label=p, command=lambda v=p: input_port_var.set(v))

    if inputs:
        input_port_var.set(inputs[0])

    lower_output_port_menu["menu"].delete(0, "end")
    lower_output_port_menu["menu"].add_command(label="", command=lambda v="": lower_output_port_var.set(v))
    for p in outputs:
        lower_output_port_menu["menu"].add_command(label=p, command=lambda v=p: lower_output_port_var.set(v))

    upper_output_port_menu["menu"].delete(0, "end")
    upper_output_port_menu["menu"].add_command(label="", command=lambda v="": upper_output_port_var.set(v))
    for p in outputs:
        upper_output_port_menu["menu"].add_command(label=p, command=lambda v=p: upper_output_port_var.set(v))

ttk.Button(tab_ports, text="Refresh Ports", command=refresh_ports).grid(
    row=1, column=0, columnspan=2, pady=ui["pady"]
)

tab_ports.columnconfigure(1, weight=1)

# ---------------- Program Change Tab ----------------

# Program Change Tab
#
# Allows sending Program Change messages to lower and upper zones, and
# loading General MIDI instrument definition files.
#
# Features
# --------
# - Lower/upper Program Change dropdowns
# - Buttons to send Program Change messages
# - Dropdowns for selecting GM instrument definition files (`*.gm.json`)
# - "Refresh Instruments" button to rescan GM files
# - Automatic rebuilding of program dropdowns when instrument files change
#
# Notes
# -----
# - Program numbers are extracted using `get_program_number()`.
# - Instrument definition files map program numbers to instrument names.
# - Program Change messages are sent using `send_lower_program_change()` and
#   `send_upper_program_change()`.

tab_pc = ttk.Frame(notebook, padding=ui["padx"])
notebook.add(tab_pc, text="Program Change")

ttk.Label(tab_pc, text="Lower Zone Program:").grid(row=0, column=0, sticky="w")
lower_program_var = tk.StringVar(value="0")
lower_program_menu = ttk.OptionMenu(tab_pc, lower_program_var, "0")
lower_program_menu.grid(row=1, column=0, sticky="ew")

ttk.Button(tab_pc, text="Send Lower Program Change",
           command=send_lower_program_change).grid(
    row=2, column=0, sticky="ew", pady=(ui["pady"], 0)
)

ttk.Label(tab_pc, text="Upper Zone Program:").grid(row=0, column=1, sticky="w")
upper_program_var = tk.StringVar(value="0")
upper_program_menu = ttk.OptionMenu(tab_pc, upper_program_var, "0")
upper_program_menu.grid(row=1, column=1, sticky="ew")

ttk.Button(tab_pc, text="Send Upper Program Change",
           command=send_upper_program_change).grid(
    row=2, column=1, sticky="ew", pady=(ui["pady"], 0)
)

ttk.Label(tab_pc, text="Lower Instrument Definition File:").grid(row=3, column=0, sticky="w")
lower_instr_menu = ttk.OptionMenu(tab_pc, lower_instrument_file_var, "")
lower_instr_menu.grid(row=4, column=0, sticky="ew")

ttk.Label(tab_pc, text="Upper Instrument Definition File:").grid(row=3, column=1, sticky="w")
upper_instr_menu = ttk.OptionMenu(tab_pc, upper_instrument_file_var, "")
upper_instr_menu.grid(row=4, column=1, sticky="ew")

ttk.Button(tab_pc, text="Refresh Instruments", command=refresh_instruments).grid(
    row=5, column=0, columnspan=2, pady=ui["pady"]
)

# ---------------- Drumkits Tab ----------------
# Drumkits Tab
#
# Provides selection and sending of drumkit Program Change messages based on
# drumkit definition files (`*drumkits.gm.json`).
#
# Features
# --------
# - Dropdown for selecting drumkit definition file
# - Dropdown for selecting drumkit program number
# - Drumkit MIDI channel selector (1–16)
# - "Refresh Drumkit Files" button to rescan drumkit JSON files
# - "Send Drumkit Change" button to send Program Change
#
# Notes
# -----
# - Drumkit definitions map program numbers to drumkit names.
# - GS‑compatible drumkits may require Bank Select messages (handled in
#   `send_drumkit_change()`).

tab_drum = ttk.Frame(notebook, padding=ui["padx"])
notebook.add(tab_drum, text="Drumkits")

ttk.Label(tab_drum, text="Drumkit Definition File:").grid(row=0, column=0, sticky="w")
drumkit_file_menu = ttk.OptionMenu(tab_drum, selected_drumkit_file, "")
drumkit_file_menu.grid(row=1, column=0, sticky="ew")

ttk.Button(tab_drum, text="Refresh Drumkit Files", command=refresh_drumkit_files).grid(
    row=2, column=0, pady=ui["pady"], sticky="ew"
)

ttk.Label(tab_drum, text="Drumkit:").grid(row=3, column=0, sticky="w")
drumkit_menu = ttk.OptionMenu(tab_drum, drumkit_var, "")
drumkit_menu.grid(row=4, column=0, sticky="ew")

ttk.Label(tab_drum, text="Drumkit MIDI Channel:").grid(row=5, column=0, sticky="w")
ttk.OptionMenu(tab_drum, drumkit_channel_var, 10, *range(1,17)).grid(
    row=6, column=0, sticky="ew"
)

ttk.Button(tab_drum, text="Send Drumkit Change", command=send_drumkit_change).grid(
    row=7, column=0, pady=ui["pady"], sticky="ew"
)

# ---------------- GS Tab ----------------
# GS Bank/Reset Tab
#
# Provides controls for sending Roland GS Bank Select (MSB/LSB) and Program
# Change messages, as well as GS Reset SysEx.
#
# Features
# --------
# - Spinboxes for lower/upper Bank MSB (CC0)
# - Spinboxes for lower/upper Bank LSB (CC32)
# - Buttons to send GS Bank+Program for lower/upper zones
# - Button to send GS Reset SysEx
#
# Notes
# -----
# - GS Bank Select uses CC0 (MSB) and CC32 (LSB).
# - GS Reset SysEx resets GS‑compatible devices (e.g., SC‑55).
# - Program numbers are taken from GM instrument definitions.

tab_gs = ttk.Frame(notebook, padding=ui["padx"])
notebook.add(tab_gs, text="GS Bank/Reset")

ttk.Label(tab_gs, text="Lower GS Bank MSB (CC0):").grid(row=0, column=0, sticky="w")
lower_bank_msb_spin = tk.Spinbox(tab_gs, from_=0, to=127, textvariable=lower_bank_msb_var, width=5)
lower_bank_msb_spin.grid(row=1, column=0, sticky="w")

ttk.Label(tab_gs, text="Lower GS Bank LSB (CC32):").grid(row=0, column=1, sticky="w")
lower_bank_lsb_spin = tk.Spinbox(tab_gs, from_=0, to=127, textvariable=lower_bank_lsb_var, width=5)
lower_bank_lsb_spin.grid(row=1, column=1, sticky="w")

ttk.Button(tab_gs, text="Send Lower GS Bank+Program",
           command=lambda: send_gs_bank_and_program(lower=True)).grid(
    row=2, column=0, columnspan=2, pady=ui["pady"]
)

ttk.Label(tab_gs, text="Upper GS Bank MSB (CC0):").grid(row=3, column=0, sticky="w")
upper_bank_msb_spin = tk.Spinbox(tab_gs, from_=0, to=127, textvariable=upper_bank_msb_var, width=5)
upper_bank_msb_spin.grid(row=4, column=0, sticky="w")

ttk.Label(tab_gs, text="Upper GS Bank LSB (CC32):").grid(row=3, column=1, sticky="w")
upper_bank_lsb_spin = tk.Spinbox(tab_gs, from_=0, to=127, textvariable=upper_bank_lsb_var, width=5)
upper_bank_lsb_spin.grid(row=4, column=1, sticky="w")

ttk.Button(tab_gs, text="Send Upper GS Bank+Program",
           command=lambda: send_gs_bank_and_program(lower=False)).grid(
    row=5, column=0, columnspan=2, pady=ui["pady"]
)

ttk.Button(tab_gs, text="Send GS Reset (SysEx)", command=send_gs_reset).grid(
    row=6, column=0, columnspan=2, pady=ui["pady"]
)

# ---------------- Song Presets Tab ----------------
# Song Presets Tab
# 
# Allows saving, loading, and deleting named song presets. A preset stores:
#
# - Split point
# - Zone channels
# - Transpose values
# - Input/output ports
# - Instrument definition files
# - Program numbers
# - GS bank MSB/LSB
# - Drumkit file, drumkit selection, drumkit channel
#
# Features
# --------
# - Entry for preset name
# - Buttons to save/delete presets
# - Dropdown to select existing presets
# - Button to load selected preset
#
# Notes
# -----
# - Presets are stored in `midimodifier_songs.json`.
# - Presets allow instant recall of complex routing setups.

tab_presets = ttk.Frame(notebook, padding=ui["padx"])
notebook.add(tab_presets, text="Song Presets")

ttk.Label(tab_presets, text="Song Name:").grid(row=0, column=0, sticky="w")
song_entry = ttk.Entry(tab_presets, textvariable=song_name_var, width=30)
song_entry.grid(row=0, column=1, sticky="ew", padx=(5, 5))

ttk.Button(tab_presets, text="Save Song Preset", command=save_song_preset).grid(row=0, column=2, padx=5)
ttk.Button(tab_presets, text="Delete Song", command=delete_song_preset).grid(row=0, column=3, padx=5)

ttk.Label(tab_presets, text="Select Song:").grid(row=1, column=0, sticky="w")
song_combo = ttk.Combobox(tab_presets, width=30, state="readonly")
song_combo.grid(row=1, column=1, sticky="ew", padx=(5, 5))
ttk.Button(tab_presets, text="Load Song Preset", command=load_selected_song_preset).grid(row=1, column=2, padx=5)

tab_presets.columnconfigure(1, weight=1)

# ---------------- Setlists Tab ----------------
"""
# Setlists Tab

Allows creation, editing, and playback of setlists. A setlist is an
ordered list of song presets.

Features
--------
- Entry for setlist name
- Buttons to create/update/delete setlists
- Dropdown to select existing setlists
- Buttons to start setlist playback and advance to next song
- Text editor for comma‑separated song names

Notes
-----
- Setlists are stored in `midimodifier_songs.json`.
- Starting a setlist loads the first song preset.
- "Next Song" loads the next preset in sequence.
"""

tab_setlists = ttk.Frame(notebook, padding=ui["padx"])
notebook.add(tab_setlists, text="Setlists")

ttk.Label(tab_setlists, text="Setlist Name:").grid(row=0, column=0, sticky="w")
setlist_entry = ttk.Entry(tab_setlists, textvariable=setlist_name_var, width=30)
setlist_entry.grid(row=0, column=1, sticky="ew", padx=(5, 5))

ttk.Button(tab_setlists, text="Create/Update Setlist", command=create_update_setlist).grid(row=0, column=2, padx=5)
ttk.Button(tab_setlists, text="Delete Setlist", command=delete_setlist).grid(row=0, column=3, padx=5)

ttk.Label(tab_setlists, text="Select Setlist:").grid(row=1, column=0, sticky="w")
setlist_combo = ttk.Combobox(tab_setlists, width=30, state="readonly")
setlist_combo.grid(row=1, column=1, sticky="ew", padx=(5, 5))

ttk.Button(tab_setlists, text="Start Setlist", command=start_setlist).grid(row=1, column=2, padx=5)
ttk.Button(tab_setlists, text="Next Song", command=next_song_in_setlist).grid(row=1, column=3, padx=5)

editor_frame = ttk.LabelFrame(tab_setlists, text="Setlist Songs (comma-separated)")
editor_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(ui["pady"], 0))

setlist_songs_text = tk.Text(editor_frame, height=6)
setlist_songs_text.pack(fill="both", expand=True, padx=5, pady=5)

tab_setlists.columnconfigure(1, weight=1)
tab_setlists.rowconfigure(2, weight=1)

# ---------------- Init presets/setlists ----------------
"""
# Preset and Setlist Initialization

Loads the JSON configuration file (`midimodifier_songs.json`) and populates:

- Song presets dropdown (`song_combo`)
- Setlist dropdown (`setlist_combo`)

This ensures that all saved presets and setlists are available immediately
when the application starts.

Notes
-----
- If the JSON file does not exist, an empty configuration is created.
- This block must run before the main event loop.
"""

load_song_config()
refresh_song_list()
refresh_setlist_list()

# ---------------- Main Loop ----------------
"""
# Main Application Loop

Starts the Tkinter event loop, which keeps the GUI responsive and active.
This loop:

- Handles button presses, dropdown selections, and text updates.
- Keeps the routing engine’s status indicators updated.
- Allows real‑time MIDI monitoring in the Routing tab.
- Enables live editing of presets, setlists, drumkits, and GS settings.

Notes
-----
- The routing engine runs in a background thread (`router_thread`).
- Tkinter’s event loop remains active until the user closes the window.
- All GUI tabs remain fully interactive during routing.
"""

root.mainloop()

