import mido
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

running = False
router_thread = None

# ---------------- Message Filter ----------------

def message_matches_filter(msg, filter_value):
    if filter_value == "All":
        return True
    if filter_value == "Notes" and msg.type in ("note_on", "note_off"):
        return True
    if filter_value == "CC" and msg.type == "control_change":
        return True
    if filter_value == "Pitch Bend" and msg.type == "pitchwheel":
        return True
    if filter_value == "Aftertouch" and msg.type in ("aftertouch", "polytouch"):
        return True
    if filter_value == "Program Change" and msg.type == "program_change":
        return True
    return False

# ---------------- Router Control ----------------

def start_router():
    global running, router_thread
    if running:
        return
    running = True
    router_thread = threading.Thread(target=router_loop, daemon=True)
    router_thread.start()
    log_main("Router started.")

def stop_router():
    global running
    running = False
    log_main("Router stopped.")

# ---------------- Routing Loop ----------------

def router_loop():
    selected_input = input_port_var.get().strip()
    selected_output = output_port_var.get().strip()

    inport = mido.open_input(selected_input) if selected_input else None
    outport = mido.open_output(selected_output) if selected_output else None

    if not selected_input:
        log_main("No input port selected.")
    if not selected_output:
        log_main("No output port selected.")

    while running:
        if inport:
            for msg in inport.iter_pending():

                # Incoming monitor
                if message_matches_filter(msg, incoming_filter_var.get()):
                    log_in(str(msg))

                # Read routing settings
                try:
                    split = int(split_var.get())
                except ValueError:
                    split = 60

                lower_choice = lower_zone_var.get()
                upper_choice = upper_zone_var.get()

                original = msg.copy()

                # Two-zone routing logic
                if msg.type in ("note_on", "note_off"):
                    if msg.note < split:
                        if lower_choice != "Unchanged":
                            msg.channel = int(lower_choice) - 1
                    else:
                        if upper_choice != "Unchanged":
                            msg.channel = int(upper_choice) - 1

                # Outgoing monitor
                if message_matches_filter(msg, outgoing_filter_var.get()):
                    log_out(str(msg))

                # Send if output exists
                if outport:
                    outport.send(msg)

                # Status bar update
                if msg.type in ("note_on", "note_off"):
                    out_ch = f"ch{msg.channel+1}" if outport else "(no output)"
                    status_var.set(
                        f"IN: {original.type} {original.note} ch{original.channel+1}   "
                        f"OUT: {msg.type} {msg.note} {out_ch}   "
                        f"Split: {split}   Lower→{lower_choice} Upper→{upper_choice}"
                    )

# ---------------- Logging Helpers ----------------

def log_main(text):
    main_log.insert(tk.END, text + "\n")
    main_log.see(tk.END)

def log_in(text):
    in_log.insert(tk.END, text + "\n")
    in_log.see(tk.END)

def log_out(text):
    out_log.insert(tk.END, text + "\n")
    out_log.see(tk.END)

# ---------------- GUI Setup ----------------

root = tk.Tk()
root.title("MIDI Router with Monitoring")

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

# ---------------- Routing Tab ----------------

tab_route = ttk.Frame(notebook, padding=10)
notebook.add(tab_route, text="Routing")

# Split point centered
ttk.Label(tab_route, text="Split Point (0–127):").grid(row=0, column=0, columnspan=2)
split_var = tk.StringVar(value="60")
ttk.Entry(tab_route, textvariable=split_var, width=8, justify="center").grid(row=1, column=0, columnspan=2, pady=5)

# Lower and Upper zone routing
ttk.Label(tab_route, text="Lower Zone Channel:").grid(row=2, column=0, sticky="w")
ttk.Label(tab_route, text="Upper Zone Channel:").grid(row=2, column=1, sticky="e")

zone_options = ["Unchanged"] + [str(i) for i in range(1, 17)]

lower_zone_var = tk.StringVar(value="Unchanged")
upper_zone_var = tk.StringVar(value="Unchanged")

ttk.OptionMenu(tab_route, lower_zone_var, "Unchanged", *zone_options).grid(row=3, column=0, sticky="w")
ttk.OptionMenu(tab_route, upper_zone_var, "Unchanged", *zone_options).grid(row=3, column=1, sticky="e")

# Start/Stop
ttk.Button(tab_route, text="Start", command=start_router).grid(row=4, column=0, pady=10)
ttk.Button(tab_route, text="Stop", command=stop_router).grid(row=4, column=1, pady=10)

# Main log
main_log = scrolledtext.ScrolledText(tab_route, width=60, height=15)
main_log.grid(row=5, column=0, columnspan=2, pady=10)

# ---------------- Incoming MIDI Tab ----------------

tab_in = ttk.Frame(notebook, padding=10)
notebook.add(tab_in, text="Incoming MIDI")

incoming_filter_var = tk.StringVar(value="All")
ttk.Label(tab_in, text="Show:").pack(anchor="w")
ttk.OptionMenu(tab_in, incoming_filter_var, "All", "All", "Notes", "CC", "Pitch Bend", "Aftertouch", "Program Change").pack(anchor="w")

in_log = scrolledtext.ScrolledText(tab_in, width=60, height=20)
in_log.pack(fill="both", expand=True)

# ---------------- Outgoing MIDI Tab ----------------

tab_out = ttk.Frame(notebook, padding=10)
notebook.add(tab_out, text="Outgoing MIDI")

outgoing_filter_var = tk.StringVar(value="All")
ttk.Label(tab_out, text="Show:").pack(anchor="w")
ttk.OptionMenu(tab_out, outgoing_filter_var, "All", "All", "Notes", "CC", "Pitch Bend", "Aftertouch", "Program Change").pack(anchor="w")

out_log = scrolledtext.ScrolledText(tab_out, width=60, height=20)
out_log.pack(fill="both", expand=True)

# ---------------- MIDI Ports Tab ----------------

def refresh_ports():
    inputs = mido.get_input_names()
    outputs = mido.get_output_names()

    input_menu['menu'].delete(0, 'end')
    for p in inputs:
        input_menu['menu'].add_command(label=p, command=lambda v=p: input_port_var.set(v))

    output_menu['menu'].delete(0, 'end')
    for p in outputs:
        output_menu['menu'].add_command(label=p, command=lambda v=p: output_port_var.set(v))

tab_ports = ttk.Frame(notebook, padding=10)
notebook.add(tab_ports, text="MIDI Ports")

ttk.Label(tab_ports, text="Input Port:").grid(row=0, column=0, sticky="w")
input_port_var = tk.StringVar(value="")
input_menu = ttk.OptionMenu(tab_ports, input_port_var, "")
input_menu.grid(row=0, column=1, sticky="ew")

ttk.Label(tab_ports, text="Output Port:").grid(row=1, column=0, sticky="w")
output_port_var = tk.StringVar(value="")
output_menu = ttk.OptionMenu(tab_ports, output_port_var, "")
output_menu.grid(row=1, column=1, sticky="ew")

ttk.Button(tab_ports, text="Refresh Ports", command=refresh_ports).grid(row=2, column=0, columnspan=2, pady=10)

# ---------------- Status Bar ----------------

status_var = tk.StringVar(value="Ready.")
status_bar = ttk.Label(root, textvariable=status_var, relief="sunken", anchor="w")
status_bar.pack(fill="x", side="bottom")

# ---------------- Main Loop ----------------

root.mainloop()
