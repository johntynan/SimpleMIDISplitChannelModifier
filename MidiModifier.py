import mido
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import os
import json

running = False
router_thread = None

# ---------------- Paths for presets/setlists ----------------
SONG_CONFIG_PATH = os.path.join(os.getcwd(), "midimodifier_songs.json")

# ---------------- UI AUTO-DETECT ----------------
def ui_scale(root):
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
    global running, router_thread
    if running:
        return
    running = True
    router_status_var.set("Router started.")
    router_thread = threading.Thread(target=router_loop, daemon=True)
    router_thread.start()

def stop_router():
    global running
    running = False
    router_status_var.set("Router stopped.")

# ---------------- Routing Loop ----------------
def router_loop():
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
    menu = lower_program_menu["menu"]
    menu.delete(0, "end")

    for name in lower_instrument_names:
        menu.add_command(label=name, command=lambda v=name: lower_program_var.set(v))

    if lower_instrument_names:
        lower_program_var.set(lower_instrument_names[0])
    else:
        lower_program_var.set("0")

def rebuild_upper_program_dropdown():
    menu = upper_program_menu["menu"]
    menu.delete(0, "end")

    for name in upper_instrument_names:
        menu.add_command(label=name, command=lambda v=name: upper_program_var.set(v))

    if upper_instrument_names:
        upper_program_var.set(upper_instrument_names[0])
    else:
        upper_program_var.set("0")

def refresh_instruments():
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
    try:
        return int(var.get().split(" - ")[0])
    except:
        return 0

def send_lower_program_change():
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
    try:
        with open(SONG_CONFIG_PATH, "w") as f:
            json.dump(song_cfg, f, indent=4)
    except:
        pass

def save_song_preset():
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
    songs = sorted(song_cfg.get("songs", {}).keys())
    song_combo["values"] = songs

def delete_song_preset():
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
    name = song_combo.get().strip()
    if not name:
        router_status_var.set("Select a song to load.")
        return
    song_name_var.set(name)
    load_song_preset(name)

def refresh_setlist_list():
    setlists = sorted(song_cfg.get("setlists", {}).keys())
    setlist_combo["values"] = setlists

def create_update_setlist():
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
load_song_config()
refresh_song_list()
refresh_setlist_list()

# ---------------- Main Loop ----------------
root.mainloop()
