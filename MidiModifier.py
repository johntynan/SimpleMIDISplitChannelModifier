import mido
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

running = False
router_thread = None

# ---------------- Transpose Map ----------------

transpose_map = {
    "+ 2 octaves": 24,
    "+ 1 octave": 12,
    "+ 11 semitones": 11,
    "+ 10 semitones": 10,
    "+ 9 semitones": 9,
    "+ 8 semitones": 8,
    "+ 7 semitones": 7,
    "+ 6 semitones": 6,
    "+ 5 semitones": 5,
    "+ 4 semitones": 4,
    "+ 3 semitones": 3,
    "+ 2 semitones": 2,
    "+ 1 semitone": 1,
    "0": 0,
    "- 1 semitone": -1,
    "- 2 semitones": -2,
    "- 3 semitones": -3,
    "- 4 semitones": -4,
    "- 5 semitones": -5,
    "- 6 semitones": -6,
    "- 7 semitones": -7,
    "- 8 semitones": -8,
    "- 9 semitones": -9,
    "- 10 semitones": -10,
    "- 11 semitones": -11,
    "- 1 octave": -12,
    "- 2 octaves": -24,
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

                # ---------------- Zone Selection ----------------
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

                    # Apply transpose
                    msg.note = max(0, min(127, msg.note + transpose_amount))

                    # Apply channel remap
                    if out_channel != "Unchanged":
                        msg.channel = int(out_channel) - 1

                    # Send + monitor
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
                    # Non-note messages go to both ports
                    if out_lower:
                        out_lower.send(msg)
                    if out_upper:
                        out_upper.send(msg)

# ---------------- GUI SETUP ----------------

root = tk.Tk()
root.title("MIDI Router with Monitoring")

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

# ---------------- Routing Tab ----------------

tab = ttk.Frame(notebook, padding=10)
notebook.add(tab, text="Routing")

# ---------------- DEFINE ALL VARIABLES FIRST ----------------

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

# ---------------- GUI ELEMENTS ----------------

# Panic button
panic_button = ttk.Button(tab, text="Panic", command=panic)
panic_button.grid(row=0, column=0, columnspan=2, pady=(0, 5))

# Split point label + spinbox
ttk.Label(tab, text="Split Point (0–127):").grid(row=1, column=0, columnspan=2)
split_spin = tk.Spinbox(tab, from_=0, to=127, textvariable=split_var, width=5)
split_spin.grid(row=2, column=0, columnspan=2, pady=5)

# Start/Stop
start_button = ttk.Button(tab, text="Start", command=start_router)
stop_button = ttk.Button(tab, text="Stop", command=stop_router)
start_button.grid(row=3, column=0, pady=5, sticky="e")
stop_button.grid(row=3, column=1, pady=5, sticky="w")

# Router status bar (centered)
status_frame = ttk.Frame(tab)
status_frame.grid(row=4, column=0, columnspan=2, pady=(0, 10))
status_label = ttk.Label(status_frame, textvariable=router_status_var, relief="sunken", anchor="w", width=40)
status_label.pack()

# --- Callback (now safe) ---
def update_split_point(*args):
    router_status_var.set(f"Split point set to {split_var.get()}")

split_var.trace_add("write", update_split_point)

# Transpose
ttk.Label(tab, text="Transpose Lower Zone:").grid(row=5, column=0, sticky="w")
ttk.Label(tab, text="Transpose Upper Zone:").grid(row=5, column=1, sticky="e")

lower_transpose_dropdown = create_scrollable_dropdown(tab, lower_transpose_var, transpose_options)
upper_transpose_dropdown = create_scrollable_dropdown(tab, upper_transpose_var, transpose_options)

lower_transpose_dropdown.grid(row=6, column=0, sticky="w")
upper_transpose_dropdown.grid(row=6, column=1, sticky="e")

# Channels
ttk.Label(tab, text="Lower Zone Channel:").grid(row=7, column=0, sticky="w")
ttk.Label(tab, text="Upper Zone Channel:").grid(row=7, column=1, sticky="e")

ttk.OptionMenu(tab, lower_zone_var, "Unchanged", *zone_options).grid(row=8, column=0, sticky="w")
ttk.OptionMenu(tab, upper_zone_var, "Unchanged", *zone_options).grid(row=8, column=1, sticky="e")

# Output channel labels
ttk.Label(tab, textvariable=lower_output_var).grid(row=9, column=0, sticky="w")
ttk.Label(tab, textvariable=upper_output_var).grid(row=9, column=1, sticky="e")

# Output ports
ttk.Label(tab, text="Lower Zone Output Port:").grid(row=10, column=0, sticky="w")
ttk.Label(tab, text="Upper Zone Output Port:").grid(row=10, column=1, sticky="e")

lower_output_port_menu = ttk.OptionMenu(tab, lower_output_port_var, "")
upper_output_port_menu = ttk.OptionMenu(tab, upper_output_port_var, "")

lower_output_port_menu.grid(row=11, column=0, sticky="ew")
upper_output_port_menu.grid(row=11, column=1, sticky="ew")

# LOWER OUTPUT + STATUS
ttk.Label(tab, text="Lower Zone Output:").grid(row=12, column=0, sticky="w")
lower_output_monitor = scrolledtext.ScrolledText(tab, width=30, height=6)
lower_output_monitor.grid(row=13, column=0, sticky="nsew", padx=(0, 5))

ttk.Label(tab, text="Lower Zone Status:").grid(row=14, column=0, sticky="w")
lower_status_var = tk.StringVar(value="Lower zone idle.")
ttk.Label(tab, textvariable=lower_status_var, relief="sunken", anchor="w").grid(
    row=15, column=0, sticky="ew", padx=(0, 5), pady=(0, 5)
)

# UPPER OUTPUT + STATUS
ttk.Label(tab, text="Upper Zone Output:").grid(row=12, column=1, sticky="e")
upper_output_monitor = scrolledtext.ScrolledText(tab, width=30, height=6)
upper_output_monitor.grid(row=13, column=1, sticky="nsew", padx=(5, 0))

ttk.Label(tab, text="Upper Zone Status:").grid(row=14, column=1, sticky="e")
upper_status_var = tk.StringVar(value="Upper zone idle.")
ttk.Label(tab, textvariable=upper_status_var, relief="sunken", anchor="w").grid(
    row=15, column=1, sticky="ew", padx=(5, 0), pady=(0, 5)
)

# Stretch rows
tab.rowconfigure(13, weight=1)
tab.columnconfigure(0, weight=1)
tab.columnconfigure(1, weight=1)

# ---------------- MIDI Ports Tab ----------------

tab_ports = ttk.Frame(notebook, padding=10)
notebook.add(tab_ports, text="MIDI Ports")

ttk.Label(tab_ports, text="Input Port:").grid(row=0, column=0, sticky="w")
input_port_var = tk.StringVar(value="")
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
    row=1, column=0, columnspan=2, pady=10
)

tab_ports.columnconfigure(1, weight=1)

# ---------------- Main Loop ----------------

root.mainloop()
