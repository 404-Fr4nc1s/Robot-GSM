#!/usr/bin/env/python
# File : GUI_adeept.py
# GUI for robot control (Adeept PiCar Pro)
# Updated and unified with modern core (client_core.py)
# Author: Zencoder Assistant - 2025

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import socket
import webbrowser

import client_core_test_mod as core


# -----------------------------------------------------
# ROOT WINDOW SETUP
# -----------------------------------------------------

class RobotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Adeept PiCar Pro - New GUI")
        self.root.geometry("1100x720")
        self.root.configure(bg="#101010")

        core.register_root(self.root)

        # Connection state
        self.server_ip = tk.StringVar(value="192.168.4.1")
        self.server_port = tk.IntVar(value=10223)

        # Build frames
        self.build_connection_frame()
        self.build_dashboard_frame()
        self.build_control_frame()
        self.build_sound_frame()
        self.build_log_frame()

        # Launch telemetry loop
        self.root.after(1000, core.telemetry_loop)

    def open_camera_browser(self):
        ip = self.server_ip.get().strip()
        if not ip:
            messagebox.showerror("Erreur", "IP du serveur vide.")
            return
        url = f"http://{ip}:5000"
        core.append_log(f"Ouverture navigateur : {url}")
        webbrowser.open(url)

    # -------------------------------------------------
    # CONNECTION BLOCK
    # -------------------------------------------------
    def build_connection_frame(self):
        frame = tk.LabelFrame(self.root, text="Connexion Serveur", bg="#1e1e1e", fg="white")
        frame.pack(fill="x", pady=5, padx=10)

        tk.Label(frame, text="IP :", fg="white", bg="#1e1e1e").grid(row=0, column=0, padx=3)
        tk.Entry(frame, textvariable=self.server_ip, width=15).grid(row=0, column=1, padx=3)

        tk.Label(frame, text="Port :", fg="white", bg="#1e1e1e").grid(row=0, column=2, padx=3)
        tk.Entry(frame, textvariable=self.server_port, width=6).grid(row=0, column=3, padx=3)

        ttk.Button(frame, text="Connexion", command=self.connect_server).grid(row=0, column=4, padx=10)
        ttk.Button(frame, text="Déconnexion", command=self.disconnect_server).grid(row=0, column=5, padx=10)
        ttk.Button(frame, text="Caméra (Web)", command=self.open_camera_browser).grid(row=0, column=6, padx=10)

    # -------------------------------------------------
    # DASHBOARD FRAME
    # -------------------------------------------------
    def build_dashboard_frame(self):
        frame = tk.LabelFrame(self.root, text="Dashboard Robot", bg="#1e1e1e", fg="white")
        frame.pack(fill="x", pady=5, padx=10)

        banner = tk.Label(frame, text="Robot non connecté", bg="#333333", fg="white", font=("Arial", 12), height=2)
        banner.pack(fill="x", padx=5, pady=5)
        core.ensure_banner(banner)
        
        # Store banner for state updates
        self.banner = banner

        # Info rows
        info_frame = tk.Frame(frame, bg="#1e1e1e")
        info_frame.pack(fill="x")

        tk.Label(info_frame, text="IP :", bg="#1e1e1e", fg="white").grid(row=0, column=0, sticky="w")
        ip_lbl = tk.Label(info_frame, text="-", fg="#00FFAA", bg="#1e1e1e")
        ip_lbl.grid(row=0, column=1, sticky="w")

        tk.Label(info_frame, text="Temp CPU :", bg="#1e1e1e", fg="white").grid(row=1, column=0, sticky="w")
        cput_lbl = tk.Label(info_frame, text="-", fg="#00FFAA", bg="#1e1e1e")
        cput_lbl.grid(row=1, column=1, sticky="w")

        tk.Label(info_frame, text="CPU :", bg="#1e1e1e", fg="white").grid(row=2, column=0, sticky="w")
        cpu_lbl = tk.Label(info_frame, text="-", fg="#00FFAA", bg="#1e1e1e")
        cpu_lbl.grid(row=2, column=1, sticky="w")

        tk.Label(info_frame, text="RAM :", bg="#1e1e1e", fg="white").grid(row=3, column=0, sticky="w")
        ram_lbl = tk.Label(info_frame, text="-", fg="#00FFAA", bg="#1e1e1e")
        ram_lbl.grid(row=3, column=1, sticky="w")

        tk.Label(info_frame, text="Uptime :", bg="#1e1e1e", fg="white").grid(row=4, column=0, sticky="w")
        up_lbl = tk.Label(info_frame, text="-", fg="#00FFAA", bg="#1e1e1e")
        up_lbl.grid(row=4, column=1, sticky="w")

        core.ensure_status_labels(ip_lbl, cput_lbl, cpu_lbl, ram_lbl, up_lbl)
        
        # Periodic check for connection state to update UI
        self.root.after(500, self.check_connection_state)

    def check_connection_state(self):
        """
        Updates UI based on connection status.
        """
        if core.get_tcp_socket() is None:
            self.banner.config(text="⚠️ Robot DÉCONNECTÉ", bg="#B71C1C")
            # Disable controls if needed, or just show visual cue
        else:
            # Connected state is handled by telemetry updates usually, 
            # but we can enforce a "Connected" state if telemetry is lagging
            pass
        self.root.after(500, self.check_connection_state)

    # -------------------------------------------------
    # CONTROL FRAME (manual / arrows / manette)
    # -------------------------------------------------
    def build_control_frame(self):
        frame = tk.LabelFrame(self.root, text="Contrôles Robot", bg="#1e1e1e", fg="white")
        frame.pack(fill="x", pady=5, padx=10)

        # Mode selection (Direct / Clavier / Manette)
        mode_frame = tk.Frame(frame, bg="#1e1e1e")
        mode_frame.pack(pady=5)

        core.mode_var = tk.StringVar(value="Manette")

        modes = ["Direct", "Clavier", "Manette"]
        for i, m in enumerate(modes):
            rb = ttk.Radiobutton(mode_frame, text=m, value=m, variable=core.mode_var,
                                 command=lambda idx=i: self.change_mode(idx))
            rb.pack(side="left", padx=10)

        # Helper for mode-restricted key bindings
        def key_cmd(cmd, mode_req=1):
            if core.control_state.mode_index == mode_req:
                core.send_command(cmd)

        # Speed Slider
        speed_frame = tk.Frame(frame, bg="#1e1e1e")
        speed_frame.pack(pady=5)
        tk.Label(speed_frame, text="Vitesse :", bg="#1e1e1e", fg="white").pack(side="left")
        self.speed_scale = tk.Scale(speed_frame, from_=0, to=100, orient="horizontal", 
                                    bg="#1e1e1e", fg="white", highlightthickness=0,
                                    command=self.update_speed)
        self.speed_scale.set(core.control_state.speed)
        self.speed_scale.pack(side="left", padx=5)

        # Arrows for manual control (keyboard-like)
        arrows = tk.Frame(frame, bg="#1e1e1e")
        arrows.pack(pady=10)

        # Bind keyboard events to root (Clavier mode only)
        self.root.bind('<KeyPress-z>', lambda e: key_cmd("forward"))
        self.root.bind('<KeyRelease-z>', lambda e: key_cmd("DS"))
        
        self.root.bind('<KeyPress-s>', lambda e: key_cmd("backward"))
        self.root.bind('<KeyRelease-s>', lambda e: key_cmd("DS"))
        
        self.root.bind('<KeyPress-q>', lambda e: key_cmd("left"))
        self.root.bind('<KeyRelease-q>', lambda e: key_cmd("TS"))
        
        self.root.bind('<KeyPress-d>', lambda e: key_cmd("right"))
        self.root.bind('<KeyRelease-d>', lambda e: key_cmd("TS"))

        # Head / Look (Servo 1)
        self.root.bind('<KeyPress-j>', lambda e: key_cmd("lookleft"))
        self.root.bind('<KeyRelease-j>', lambda e: key_cmd("LRstop"))
        
        self.root.bind('<KeyPress-l>', lambda e: key_cmd("lookright"))
        self.root.bind('<KeyRelease-l>', lambda e: key_cmd("LRstop"))

        # Arm Lower (Servo 2)
        self.root.bind('<KeyPress-i>', lambda e: key_cmd("armup"))
        self.root.bind('<KeyRelease-i>', lambda e: key_cmd("armstop"))
        
        self.root.bind('<KeyPress-k>', lambda e: key_cmd("armdown"))
        self.root.bind('<KeyRelease-k>', lambda e: key_cmd("armstop"))

        # Arm Upper / Hand (Servo 3)
        self.root.bind('<KeyPress-p>', lambda e: key_cmd("handup"))
        self.root.bind('<KeyRelease-p>', lambda e: key_cmd("HAstop"))
        
        self.root.bind('<KeyPress-m>', lambda e: key_cmd("handdown"))
        self.root.bind('<KeyRelease-m>', lambda e: key_cmd("HAstop"))
        
        # Grip (Servo 4)
        self.root.bind('<KeyPress-u>', lambda e: key_cmd("loose"))
        self.root.bind('<KeyRelease-u>', lambda e: key_cmd("gripStop"))
        
        self.root.bind('<KeyPress-o>', lambda e: key_cmd("grab"))
        self.root.bind('<KeyRelease-o>', lambda e: key_cmd("gripStop"))

        # Calibration (V / B)
        self.root.bind('<KeyPress-v>', lambda e: key_cmd("cali_left"))
        self.root.bind('<KeyPress-b>', lambda e: key_cmd("cali_right"))

        # Emergency Stop (X) - Replaced A by X for AZERTY comfort
        self.root.bind('<KeyPress-x>', lambda e: core.emergency_stop() if core.control_state.mode_index != 0 else None)

        # Special Modes Toggles (E, R, T, G)
        self.root.bind('<KeyPress-e>', lambda e: core.toggle_mode("police") if core.control_state.mode_index == 1 else None)
        self.root.bind('<KeyPress-r>', lambda e: core.toggle_mode("r2d2") if core.control_state.mode_index == 1 else None)
        self.root.bind('<KeyPress-t>', lambda e: core.toggle_mode("disco") if core.control_state.mode_index == 1 else None)
        self.root.bind('<KeyPress-g>', lambda e: core.get_motion() if core.control_state.mode_index == 1 else None)

        ttk.Button(arrows, text="↑ (Z)", width=5, command=lambda: core.send_command("forward")).grid(row=0, column=1)
        ttk.Button(arrows, text="← (Q)", width=5, command=lambda: core.send_command("left")).grid(row=1, column=0)
        ttk.Button(arrows, text="→ (D)", width=5, command=lambda: core.send_command("right")).grid(row=1, column=2)
        ttk.Button(arrows, text="↓ (S)", width=5, command=lambda: core.send_command("backward")).grid(row=2, column=1)
        ttk.Button(arrows, text="STOP", width=8, command=lambda: core.send_command("stop")).grid(row=1, column=1, pady=5)
        tk.Button(arrows, text="URGENCE (X)", width=10, bg="red", fg="white", command=core.emergency_stop).grid(row=3, column=1, pady=5)

        # Arm controls
        arm = tk.Frame(frame, bg="#1e1e1e")
        arm.pack(pady=10)

        # Head (Servo 1)
        tk.Label(arm, text="Tête :", bg="#1e1e1e", fg="white").grid(row=0, column=0)
        ttk.Button(arm, text="⟲ (J)", width=5, command=lambda: core.send_command("lookleft")).grid(row=0, column=1, padx=5)
        ttk.Button(arm, text="⟳ (L)", width=5, command=lambda: core.send_command("lookright")).grid(row=0, column=2, padx=5)
        ttk.Button(arm, text="STOP", width=5, command=lambda: core.send_command("LRstop")).grid(row=0, column=3, padx=5)

        # Arm Lower (Servo 2)
        tk.Label(arm, text="Bras Bas :", bg="#1e1e1e", fg="white").grid(row=1, column=0)
        ttk.Button(arm, text="↑ (I)", width=5, command=lambda: core.send_command("armup")).grid(row=1, column=1, padx=5)
        ttk.Button(arm, text="↓ (K)", width=5, command=lambda: core.send_command("armdown")).grid(row=1, column=2, padx=5)
        ttk.Button(arm, text="STOP", width=5, command=lambda: core.send_command("armstop")).grid(row=1, column=3, padx=5)

        # Arm Upper / Hand (Servo 3)
        tk.Label(arm, text="Main :", bg="#1e1e1e", fg="white").grid(row=2, column=0)
        ttk.Button(arm, text="↑ (P)", width=5, command=lambda: core.send_command("handup")).grid(row=2, column=1, padx=5)
        ttk.Button(arm, text="↓ (M)", width=5, command=lambda: core.send_command("handdown")).grid(row=2, column=2, padx=5)
        ttk.Button(arm, text="STOP", width=5, command=lambda: core.send_command("HAstop")).grid(row=2, column=3, padx=5)

        # Grip (Servo 4)
        grip = tk.Frame(frame, bg="#1e1e1e")
        grip.pack(pady=10)
        tk.Label(grip, text="Pince :", bg="#1e1e1e", fg="white").pack(side="left")
        ttk.Button(grip, text="Ouvrir (U)", command=lambda: core.send_command("loose")).pack(side="left", padx=10)
        ttk.Button(grip, text="Fermer (O)", command=lambda: core.send_command("grab")).pack(side="left", padx=10)
        ttk.Button(grip, text="STOP", command=lambda: core.send_command("gripStop")).pack(side="left", padx=10)

        # Calibration & System
        sys_frame = tk.Frame(frame, bg="#1e1e1e")
        sys_frame.pack(pady=10)
        
        ttk.Button(sys_frame, text="HOME Servos", command=core.servo_home).pack(side="left", padx=5)
        ttk.Button(sys_frame, text="PWM Init", command=core.pwm_init).pack(side="left", padx=5)
        ttk.Button(sys_frame, text="PWM Default", command=core.pwm_default).pack(side="left", padx=5)

        # Switches
        sw_frame = tk.LabelFrame(frame, text="Switches", bg="#1e1e1e", fg="white")
        sw_frame.pack(pady=10, fill="x", padx=10)
        for i in range(1, 4):
            f = tk.Frame(sw_frame, bg="#1e1e1e")
            f.pack(side="left", padx=10)
            tk.Label(f, text=f"SW{i}:", bg="#1e1e1e", fg="white").pack(side="left")
            ttk.Button(f, text="ON", width=4, command=lambda n=i: core.set_switch(n, True)).pack(side="left")
            ttk.Button(f, text="OFF", width=4, command=lambda n=i: core.set_switch(n, False)).pack(side="left")

        # PWM Fine Tune
        pwm_frame = tk.LabelFrame(frame, text="Réglage PWM (Servo 0-4)", bg="#1e1e1e", fg="white")
        pwm_frame.pack(pady=10, fill="x", padx=10)
        self.servo_sel = tk.IntVar(value=0)
        for i in range(5):
            tk.Radiobutton(pwm_frame, text=f"S{i}", variable=self.servo_sel, value=i, bg="#1e1e1e", fg="white", selectcolor="#333333").pack(side="left", padx=2)
        
        ttk.Button(pwm_frame, text="←", width=3, command=lambda: core.servo_fine_tune(self.servo_sel.get(), "left")).pack(side="left", padx=5)
        ttk.Button(pwm_frame, text="→", width=3, command=lambda: core.servo_fine_tune(self.servo_sel.get(), "right")).pack(side="left", padx=5)
        ttk.Button(pwm_frame, text="90°", width=4, command=lambda: core.pwm_ms(self.servo_sel.get())).pack(side="left", padx=5)

        # Modes Autonomes
        modes_frame = tk.LabelFrame(frame, text="Modes Autonomes", bg="#1e1e1e", fg="white")
        modes_frame.pack(pady=10, fill="x", padx=10)
        
        ttk.Button(modes_frame, text="Suivi Ligne", command=lambda: core.toggle_mode("trackLine")).pack(side="left", padx=5, pady=5)
        ttk.Button(modes_frame, text="Évitement", command=lambda: core.toggle_mode("automatic")).pack(side="left", padx=5, pady=5)
        ttk.Button(modes_frame, text="Suivi Objet", command=lambda: core.toggle_mode("findColor")).pack(side="left", padx=5, pady=5)
        ttk.Button(modes_frame, text="Détection Mouvement (M)", command=core.get_motion).pack(side="left", padx=5, pady=5)
        ttk.Button(modes_frame, text="STOP CV", command=core.stop_cv).pack(side="left", padx=5, pady=5)

    # -------------------------------------------------
    # SOUND MANAGEMENT
    # -------------------------------------------------
    def build_sound_frame(self):
        frame = tk.LabelFrame(self.root, text="Sons / Effets", bg="#1e1e1e", fg="white")
        frame.pack(fill="x", pady=5, padx=10)

        # Sound list
        list_frame = tk.Frame(frame, bg="#1e1e1e")
        list_frame.pack(side="left", padx=20)

        tk.Label(list_frame, text="Liste des sons :", bg="#1e1e1e", fg="white").pack()
        lb = tk.Listbox(list_frame, width=40, height=10)
        lb.pack(pady=5)

        # Buttons
        btn_frame = tk.Frame(frame, bg="#1e1e1e")
        btn_frame.pack(side="left", padx=20)

        btn_play = ttk.Button(btn_frame, text="Lire",
                              command=lambda: core.play_selected_sound(loop=False))
        btn_loop = ttk.Button(btn_frame, text="Boucle",
                              command=lambda: core.play_selected_sound(loop=True))
        btn_stop = ttk.Button(btn_frame, text="Stop", command=core.stop_sound)
        btn_refresh = ttk.Button(btn_frame, text="Rafraîchir liste", command=core.refresh_sound_list)

        btn_play.pack(fill="x", pady=3)
        btn_loop.pack(fill="x", pady=3)
        btn_stop.pack(fill="x", pady=3)
        btn_refresh.pack(fill="x", pady=3)

        # FX buttons
        fx_frame = tk.LabelFrame(frame, text="Effets lumineux / audio", bg="#1e1e1e", fg="white")
        fx_frame.pack(side="left", padx=20)

        ttk.Button(fx_frame, text="Police ON", command=lambda: core.send_command("police")).pack(fill="x", pady=3)
        ttk.Button(fx_frame, text="Police OFF", command=lambda: core.send_command("policeOff")).pack(fill="x", pady=3)
        ttk.Button(fx_frame, text="Disco ON", command=lambda: core.send_command("disco")).pack(fill="x", pady=3)
        ttk.Button(fx_frame, text="Disco OFF", command=lambda: core.send_command("discoOff")).pack(fill="x", pady=3)
        ttk.Button(fx_frame, text="R2-D2 ON", command=lambda: core.send_command("R2-D2")).pack(fill="x", pady=3)
        ttk.Button(fx_frame, text="R2-D2 OFF", command=lambda: core.send_command("R2-D2_Off")).pack(fill="x", pady=3)

        core.ensure_sound_listbox(lb, {
            "play": btn_play,
            "loop": btn_loop,
            "stop": btn_stop,
            "refresh": btn_refresh
        })

    # -------------------------------------------------
    # LOG WINDOW
    # -------------------------------------------------
    def build_log_frame(self):
        frame = tk.LabelFrame(self.root, text="Logs", bg="#1e1e1e", fg="white")
        frame.pack(fill="both", expand=True, pady=5, padx=10)

        log = scrolledtext.ScrolledText(frame, height=10, bg="#0a0a0a", fg="#00ffcc")
        log.pack(fill="both", expand=True)
        log.configure(state="disabled")

        core.ensure_log_text(log)

    # -------------------------------------------------
    # CHANGE MODE
    # -------------------------------------------------
    def change_mode(self, idx: int):
        core.control_state.mode_index = idx
        core.append_log(f"Mode changé : {core.mode_var.get()}")

    def update_speed(self, val):
        speed = int(val)
        core.control_state.speed = speed
        # Only send if not in gamepad mode (gamepad handles its own speed)
        if core.control_state.mode_index != 2:
             core.send_speed(speed)

    # -------------------------------------------------
    # CONNECT / DISCONNECT
    # -------------------------------------------------
    def connect_server(self):
        ip = self.server_ip.get().strip()
        port = int(self.server_port.get())

        if not ip:
            messagebox.showerror("Erreur", "IP du serveur vide.")
            return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ip, port))
            core.set_tcp_socket(sock)
            core.append_log(f"Connecté à {ip}:{port}")

            # start threads
            core.start_connection_threads()

            # request sound list
            self.root.after(1500, core.refresh_sound_list)

        except Exception as exc:
            messagebox.showerror("Erreur connexion", f"Impossible de se connecter :\n{exc}")
            return

    def disconnect_server(self):
        sock = core.get_tcp_socket()
        if sock:
            try:
                sock.close()
            except:
                pass
        core.set_tcp_socket(None)
        core.append_log("Déconnecté du serveur.")

    # -------------------------------------------------
    # MAIN LOOP
    # -------------------------------------------------
    def start(self):
        self.root.mainloop()


# -----------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------

if __name__ == "__main__":
    gui = RobotGUI()
    gui.start()