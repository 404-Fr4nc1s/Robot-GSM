#!/usr/bin/env/python
# File name   : client_core.py
# Core functions shared between GUI_adeept.py and GUI modern

from __future__ import annotations
import json
import math
import subprocess
import threading as thread
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import ttk

from socket import *

try:
    import pygame
except:
    pygame = None

# -----------------------------------------------------
# CONSTANTS & BASE PATHS
# -----------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
SOUND_DIR = BASE_DIR / "sound_list"
DASHBOARD_REFRESH_MS = 1000
LOG_HISTORY_LIMIT = 300
HEARTBEAT_INTERVAL = 2.0

# root master (GUI injects this)
root: Optional[tk.Misc] = None

# -----------------------------------------------------
# TELEMETRY DATA CLASS
# -----------------------------------------------------

@dataclass
class TelemetryPacket:
    cpu_temp: str = "0.0"
    cpu_use: str = "0"
    ram: str = "0"
    uptime: str = "0:00:00"
    ip: str = "-"
    motors: str = "-"
    arm: str = "-"
    gripper: str = "-"
    camera_servo: str = "-"
    leds: str = "OFF"
    camera: str = "OFF"
    modes: Dict[str, bool] = None
    banner_level: str = "info"
    banner_message: str = "🤖 Robot opérationnel"


telemetry = TelemetryPacket(
    modes={"police": False, "disco": False, "r2d2": False}
)

# -----------------------------------------------------
# CONTROL STATE
# -----------------------------------------------------

@dataclass
class ControlState:
    speed: int = 60
    mode_index: int = 0       # 0=Direct, 1=Clavier, 2=Manette
    joystick_enabled: bool = False

control_state = ControlState()

# -----------------------------------------------------
# GLOBALS
# -----------------------------------------------------
received_logs: List[str] = []
tcpClicSock: Optional[socket] = None
BUFSIZ = 1024
ADDR = None

Switch_1 = 0
Switch_2 = 0
Switch_3 = 0
function_stu = 0

# For GUI widgets (injected by GUI scripts)
banner_label: Optional[tk.Label] = None
log_text: Optional[scrolledtext.ScrolledText] = None
telemetry_widgets: Dict[str, tk.Label] = {}
mode_labels: Dict[str, tk.Label] = {}
sound_listbox: Optional[tk.Listbox] = None
sound_buttons: Dict[str, ttk.Button] = {}
mode_var: Optional[tk.StringVar] = None

# Dashboard status labels (legacy Adeept skin)
label_cpu_temp: Optional[tk.Label] = None
label_cpu_use: Optional[tk.Label] = None
label_ram: Optional[tk.Label] = None
label_ip: Optional[tk.Label] = None
label_uptime: Optional[tk.Label] = None

# Joystick
JOYSTICK = None
JOYSTICK_AVAILABLE = False
JOYSTICK_THREAD_STOP = thread.Event()
JOYSTICK_DEAD_ZONE = 0.1  # Matches test_connectique_mannette.py

# -----------------------------------------------------
# INITIALIZE JOYSTICK (pygame)
# -----------------------------------------------------

if pygame:
    print(f"[DEBUG] Pygame version: {pygame.ver}")
    try:
        pygame.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        print(f"[DEBUG] Joystick count: {count}")
        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()
            print("Joystick détecté :", js.get_name())
            JOYSTICK = js
        JOYSTICK_AVAILABLE = JOYSTICK is not None

        if JOYSTICK_AVAILABLE:
            print("→ Manette active :", JOYSTICK.get_name())
        else:
            print("Aucune manette détectée (count=0)")
    except Exception as e:
        print("Erreur initialisation joystick:", e)
        JOYSTICK_AVAILABLE = False
else:
    print("Pygame non installé (import failed), joystick indisponible.")
    JOYSTICK_AVAILABLE = False

# -----------------------------------------------------
# WIDGET REGISTRATION (GUI injecte ici des widgets Tk)
# -----------------------------------------------------

def register_root(widget: tk.Misc) -> None:
    global root
    root = widget


def ensure_banner(label: tk.Label) -> None:
    global banner_label
    banner_label = label


def ensure_log_text(widget: scrolledtext.ScrolledText) -> None:
    global log_text
    log_text = widget


def ensure_telemetry_widget(name: str, widget: tk.Label) -> None:
    telemetry_widgets[name] = widget


def ensure_mode_label(name: str, widget: tk.Label) -> None:
    mode_labels[name] = widget


def ensure_sound_listbox(widget: tk.Listbox, buttons: Dict[str, ttk.Button]) -> None:
    global sound_listbox, sound_buttons
    sound_listbox = widget
    sound_buttons = buttons


def ensure_control_mode_var(var: tk.StringVar) -> None:
    global mode_var
    mode_var = var


def ensure_status_labels(ip_label, cpu_label, cpu_use_label, ram_label, uptime_label):
    global label_ip, label_cpu_temp, label_cpu_use, label_ram, label_uptime
    label_ip = ip_label
    label_cpu_temp = cpu_label
    label_cpu_use = cpu_use_label
    label_ram = ram_label
    label_uptime = uptime_label


# -----------------------------------------------------
# LOGGING / GUI LOG WINDOW
# -----------------------------------------------------

def append_log(msg: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    received_logs.append(entry)
    if len(received_logs) > LOG_HISTORY_LIMIT:
        del received_logs[0]

    if log_text:
        try:
            log_text.configure(state="normal")
            log_text.insert("end", entry + "\n")
            log_text.configure(state="disabled")
            log_text.yview_moveto(1.0)
        except:
            pass


def update_banner(level: str, msg: str) -> None:
    if not banner_label:
        return

    colors = {
        "info": "#1B5E20",
        "warning": "#FF8F00",
        "error": "#B71C1C"
    }
    color = colors.get(level, "#1B5E20")

    try:
        banner_label.config(bg=color, text=msg)
    except:
        pass


# -----------------------------------------------------
# TELEMETRY APPLY TO GUI
# -----------------------------------------------------

def apply_telemetry(data: Dict[str, object]):
    telemetry.cpu_temp = data.get("cpu_temp", telemetry.cpu_temp)
    telemetry.cpu_use = data.get("cpu_use", telemetry.cpu_use)
    telemetry.ram = data.get("ram", telemetry.ram)
    telemetry.uptime = data.get("uptime", telemetry.uptime)
    telemetry.ip = data.get("ip", telemetry.ip)
    telemetry.motors = data.get("motors", telemetry.motors)
    telemetry.arm = data.get("arm", telemetry.arm)
    telemetry.gripper = data.get("gripper", telemetry.gripper)
    telemetry.camera_servo = data.get("camera_servo", telemetry.camera_servo)
    telemetry.leds = data.get("leds", telemetry.leds)
    telemetry.camera = data.get("camera", telemetry.camera)

    modes = data.get("modes", {})
    if isinstance(modes, dict):
        telemetry.modes.update(modes)

    telemetry.banner_level = data.get("banner_level", telemetry.banner_level)
    telemetry.banner_message = data.get("banner_message", telemetry.banner_message)

    update_dashboard_labels()


def update_dashboard_labels():
    if label_ip:
        label_ip.config(text=f"IP : {telemetry.ip}")
    if label_cpu_temp:
        label_cpu_temp.config(text=f"Temp CPU : {telemetry.cpu_temp}°C")
    if label_cpu_use:
        label_cpu_use.config(text=f"CPU : {telemetry.cpu_use}%")
    if label_ram:
        label_ram.config(text=f"RAM : {telemetry.ram}%")
    if label_uptime:
        label_uptime.config(text=f"Uptime : {telemetry.uptime}")

    for name, lbl in mode_labels.items():
        active = telemetry.modes.get(name, False)
        lbl.config(
            text=f"{name} : {'ON' if active else 'OFF'}",
            fg="#00FF00" if active else "#FF3333"
        )

    update_banner(telemetry.banner_level, telemetry.banner_message)


# -----------------------------------------------------
# SOCKET MANAGEMENT
# -----------------------------------------------------

def set_tcp_socket(sock: Optional[socket]) -> None:
    global tcpClicSock, ADDR
    tcpClicSock = sock
    if sock:
        try:
            ADDR = sock.getpeername()
        except:
            pass

def get_tcp_socket() -> Optional[socket]:
    return tcpClicSock

# -----------------------------------------------------
# REQUEST TELEMETRY FROM SERVER
# -----------------------------------------------------

def request_server_info():
    if not tcpClicSock:
        return
    try:
        tcpClicSock.send("get_dashboard".encode())
    except Exception as e:
        append_log(f"Erreur requête dashboard : {e}")


def telemetry_loop():
    request_server_info()
    if root:
        root.after(DASHBOARD_REFRESH_MS, telemetry_loop)

# -----------------------------------------------------
# HEARTBEAT & AUTO-RECONNECT
# -----------------------------------------------------

HEARTBEAT_STOP = thread.Event()

def start_heartbeat_thread():
    if HEARTBEAT_STOP.is_set():
        HEARTBEAT_STOP.clear()
    t = thread.Thread(target=heartbeat_loop, daemon=True)
    t.start()

def stop_heartbeat_thread():
    HEARTBEAT_STOP.set()

def heartbeat_loop():
    """
    Sends a heartbeat JSON packet every HEARTBEAT_INTERVAL seconds.
    If sending fails, it attempts to reconnect.
    """
    global tcpClicSock, ADDR
    
    while not HEARTBEAT_STOP.is_set():
        time.sleep(HEARTBEAT_INTERVAL)
        
        if tcpClicSock:
            try:
                cmd = json.dumps({"command": "heartbeat"}) + "\n"
                tcpClicSock.send(cmd.encode())
            except Exception as e:
                append_log(f"Heartbeat failed: {e}")
                close_connection()
                # Trigger reconnection logic here if desired
                # For now, we just log it. Auto-reconnect could be complex 
                # if we don't have the IP/Port stored globally.
                # But we do have ADDR if set_tcp_socket was called.
                attempt_reconnect()
        else:
            # Not connected, try to reconnect if we have an address
            attempt_reconnect()

def attempt_reconnect():
    global tcpClicSock, ADDR
    if not ADDR:
        return

    append_log(f"Tentative de reconnexion à {ADDR}...")
    try:
        sock = socket(AF_INET, SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(ADDR)
        sock.settimeout(None)
        set_tcp_socket(sock)
        append_log("Reconnexion réussie !")
        start_connection_threads() # Restart receive thread
    except Exception:
        pass # Silent fail, will retry next heartbeat tick

def close_connection():
    global tcpClicSock
    if tcpClicSock:
        try:
            tcpClicSock.close()
        except:
            pass
    tcpClicSock = None
    append_log("Connexion fermée.")
    
    # Stop joystick thread to prevent spamming errors or commands
    JOYSTICK_THREAD_STOP.set()
    
    # Update GUI state if possible
    if root:
        try:
            # We can't directly modify GUI widgets from here easily without callbacks,
            # but the telemetry loop will fail and we can handle it there or via events.
            # For now, we rely on the GUI polling telemetry or connection status.
            pass
        except:
            pass

def start_connection_threads():
    """
    Starts the receiver thread and the heartbeat thread.
    """
    # Reset stop events
    JOYSTICK_THREAD_STOP.clear()
    
    t = thread.Thread(target=connection_thread, daemon=True)
    t.start()
    start_heartbeat_thread()
    
    # Restart joystick loop if available
    if JOYSTICK_AVAILABLE:
        thread.Thread(target=joystick_poll_loop, daemon=True).start()

def connection_thread() -> None:
    """
    Background thread that receives messages from the server and dispatches them.
    """
    global tcpClicSock, Switch_1, Switch_2, Switch_3, function_stu
    while True:
        if not tcpClicSock:
            # If socket is gone, stop this thread. 
            # The heartbeat thread will try to reconnect and restart this thread.
            break
        try:
            data = tcpClicSock.recv(BUFSIZ)
            if not data:
                # Server closed connection
                close_connection()
                break
                
            # Handle multiple JSON objects or lines
            buffer = data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    msg = line.decode("utf-8").strip()
                    if not msg:
                        continue
                    obj = json.loads(msg)
                    
                    # Dispatch based on title/command
                    if obj.get("title") == "dashboard":
                        apply_telemetry(obj.get("data", {}))
                    elif obj.get("title") == "sound_list":
                        populate_sound_list(obj.get("data", []))
                        
                except Exception:
                    pass
                    
        except Exception as exc:
            append_log(f"Erreur réception: {exc}")
            close_connection()
            break
            set_tcp_socket(None)
            break

        if not data:
            continue

        text = data.decode(errors="ignore").strip()
        append_log(f"Serveur → {text}")

        # Try JSON decode
        try:
            payload = json.loads(text)
        except Exception:
            payload = None

        if payload and isinstance(payload, dict):
            title = payload.get("title")
            if title == "dashboard":
                # server sends data inside 'data'
                apply_telemetry(payload.get("data", {}))
            elif title == "sound_list":
                populate_sound_list(payload.get("data", []))
            elif title == "scanResult":
                # legacy: radar data
                try:
                    scan_data = payload.get("data", [])
                    radar_view(30, 290, scan_data)  # legacy helper in GUI
                except Exception as e:
                    append_log(f"scanResult erreur: {e}")
            else:
                append_log(f"Packet reçu: {title}")
        else:
            # Plain text legacy responses
            if "Switch_1_on" in text:
                Switch_1 = 1
            elif "Switch_1_off" in text:
                Switch_1 = 0

            if "Switch_2_on" in text:
                Switch_2 = 1
            elif "Switch_2_off" in text:
                Switch_2 = 0

            if "Switch_3_on" in text:
                Switch_3 = 1
            elif "Switch_3_off" in text:
                Switch_3 = 0

            # stateful toggles
            if "scanResult" in text:
                try:
                    j = json.loads(text)
                    radar_view(30, 290, j.get("data", []))
                except Exception:
                    pass

def Info_receive() -> None:
    """
    Thread that periodically asks server for 'get_info' (legacy)
    """
    while True:
        if not tcpClicSock:
            break
        try:
            tcpClicSock.send("get_info".encode())
            time.sleep(3)
        except Exception as exc:
            append_log(f"Info_receive error: {exc}")
            break

def start_connection_threads() -> None:
    global JOYSTICK, JOYSTICK_AVAILABLE
    # Try to init joystick if not already done
    if not JOYSTICK_AVAILABLE and pygame:
        try:
            pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                JOYSTICK = pygame.joystick.Joystick(0)
                JOYSTICK.init()
                JOYSTICK_AVAILABLE = True
                append_log(f"Manette détectée: {JOYSTICK.get_name()}")
        except Exception as e:
            print(f"Erreur init tardive joystick: {e}")

    if tcpClicSock:
        thread.Thread(target=connection_thread, daemon=True).start()
        thread.Thread(target=Info_receive, daemon=True).start()
        if JOYSTICK_AVAILABLE:
            # Reset stop event in case it was set previously
            JOYSTICK_THREAD_STOP.clear()
            thread.Thread(target=joystick_poll_loop, daemon=True).start()
        # optional video thread
        # thread.Thread(target=video_thread, daemon=True).start()

# -----------------------------------------------------
# SEND COMMANDS / JSON helpers
# -----------------------------------------------------

def send_command(command: str) -> None:
    """
    Sends a legacy ASCII command string to the server.
    """
    if not tcpClicSock:
        append_log("❌ Pas de socket connectée.")
        return
    try:
        tcpClicSock.send(command.encode())
    except Exception as exc:
        append_log(f"Erreur envoi commande '{command}': {exc}")
        try:
            tcpClicSock.close()
        except:
            pass
        set_tcp_socket(None)


def send_json(payload: dict) -> None:
    """
    Sends a JSON payload to the server (always newline-terminated).
    """
    if not tcpClicSock:
        return
    try:
        tcpClicSock.send((json.dumps(payload) + "\n").encode())
    except Exception as exc:
        append_log(f"Erreur envoi JSON: {exc}")
        try:
            tcpClicSock.close()
        except:
            pass
        set_tcp_socket(None)


def send_speed(speed: int) -> None:
    """
    Sends the set_speed command.
    """
    if not tcpClicSock:
        return
    try:
        payload = {"command": "set_speed", "speed": int(speed)}
        send_json(payload)
    except Exception as exc:
        append_log(f"Erreur send_speed: {exc}")


def send_analog_drive(forward: float, turn: float) -> None:
    """
    Convenience: send drive_analog command with floats -1..1
    """
    if not tcpClicSock:
        return
    try:
        payload = {"command": "drive_analog", "forward": float(forward), "turn": float(turn)}
        send_json(payload)
    except Exception as exc:
        append_log(f"Erreur send_analog_drive: {exc}")


def drive_arm_analog(vertical: float, rotation: float) -> None:
    if not tcpClicSock:
        return
    try:
        payload = {"command": "arm_analog", "vertical": float(vertical), "rotate": float(rotation)}
        send_json(payload)
    except Exception as exc:
        append_log(f"Erreur drive_arm_analog: {exc}")

# -----------------------------------------------------
# SOUND HELPERS (request list, play, stop)
# -----------------------------------------------------

def refresh_sound_list() -> None:
    if sound_listbox is None:
        append_log("Widget liste sons non attaché.")
        return
    if not tcpClicSock:
        append_log("Socket non connecté: impossible de demander la liste des sons.")
        return
    try:
        tcpClicSock.send("sound_list".encode())
    except Exception as exc:
        append_log(f"Erreur demande sound_list: {exc}")

def populate_sound_list(sounds: List[str]) -> None:
    if sound_listbox is None:
        return
    try:
        sound_listbox.delete(0, "end")
        for s in sounds:
            sound_listbox.insert("end", s)
    except Exception:
        pass

def play_selected_sound(loop: bool) -> None:
    if sound_listbox is None:
        append_log("Widget liste sons non attaché.")
        return
    sel = sound_listbox.curselection()
    if not sel:
        messagebox.showinfo("Sons", "Sélectionnez un son dans la liste")
        return
    name = sound_listbox.get(sel[0])
    cmd = {"command": "sound_play_loop" if loop else "sound_play_once", "sound": name}
    send_json(cmd)

def stop_sound() -> None:
    send_json({"command": "sound_stop"})

# -----------------------------------------------------
# MISSING FEATURES FROM WEBSERVER.PY
# -----------------------------------------------------

def set_switch(num: int, state: bool) -> None:
    cmd = f"Switch_{num}_{'on' if state else 'off'}"
    send_command(cmd)

def servo_home() -> None:
    send_command("home")

def pwm_init() -> None:
    send_command("PWMINIT")

def pwm_default() -> None:
    send_command("PWMD")

def pwm_ms(servo_num: int) -> None:
    send_command(f"PWMMS{servo_num}")

def servo_fine_tune(servo_num: int, direction: str) -> None:
    """direction: 'left' or 'right'"""
    cmd = f"Si{'Left' if direction == 'left' else 'Right'}{servo_num}"
    send_command(cmd)

def stop_cv() -> None:
    send_command("stopCV")

def get_motion() -> None:
    send_command("motionGet")

# -----------------------------------------------------
# JOYSTICK POLLING & MAPPINGS
# -----------------------------------------------------

toggle_states = {"police": False, "disco": False, "r2d2": False, "trackLine": False, "automatic": False, "findColor": False}
last_button_states = {"button_0": False, "button_1": False, "button_2": False, "button_3": False}

def safe_get_hat(j) -> Tuple[int, int]:
    try:
        if hasattr(j, "get_numhats") and j.get_numhats() > 0:
            return j.get_hat(0)
    except Exception:
        pass
    return (0, 0)

def normalize_axis(value: float, dead_zone: float) -> float:
    """
    Applique une zone morte et retourne la valeur linéaire.
    Si abs(valeur) < dead_zone, retourne 0.
    Sinon, retourne la valeur brute (ex: 0.31 -> 0.31).
    """
    if abs(value) < dead_zone:
        return 0.0
    return value

def emergency_stop() -> None:
    """
    Arrêt d'urgence : coupe tout (moteurs, sons, effets).
    """
    append_log("🚨 ARRÊT D'URGENCE 🚨")
    send_command("emergency")

def toggle_mode(mode_name: str) -> None:
    """
    Toggles a special mode (police, disco, r2d2) ON/OFF.
    """
    if mode_name not in toggle_states:
        return

    toggle_states[mode_name] = not toggle_states[mode_name]
    active = toggle_states[mode_name]
    
    cmd_map = {
        "police": ("police", "policeOff"),
        "disco": ("disco", "discoOff"),
        "r2d2": ("R2-D2", "R2-D2_Off"),
        "trackLine": ("trackLine", "trackLineOff"),
        "automatic": ("automatic", "automaticOff"),
        "findColor": ("findColor", "stopCV")
    }
    
    on_cmd, off_cmd = cmd_map.get(mode_name, ("", ""))
    
    if active:
        send_command(on_cmd)
        append_log(f"Mode {mode_name} ACTIVÉ")
    else:
        send_command(off_cmd)
        append_log(f"Mode {mode_name} DÉSACTIVÉ")

def joystick_poll_loop() -> None:
    """
    Poll joystick axes/buttons and send JSON proportionnal commands.
    """
    if not JOYSTICK_AVAILABLE or JOYSTICK is None:
        append_log("Manette pas disponible: joystick loop arrêté.")
        return

    last_grip_state = "stop"  # stop, loose, grab

    while not JOYSTICK_THREAD_STOP.is_set():
        # Safety check: only send if connected and in Manette mode
        if not tcpClicSock or control_state.mode_index != 2:
            time.sleep(0.5)
            continue

        try:
            if pygame:
                pygame.event.pump()

            # axes
            # Joystick Gauche (Robot) : Zone morte 30% (0.3)
            x_axis = JOYSTICK.get_axis(0) if JOYSTICK.get_numaxes() > 0 else 0.0
            y_axis = JOYSTICK.get_axis(1) if JOYSTICK.get_numaxes() > 1 else 0.0
            
            # Joystick Droit (Bras/Rotation) : Zone morte 20% (0.2)
            arm_x = JOYSTICK.get_axis(2) if JOYSTICK.get_numaxes() > 2 else 0.0
            arm_y = JOYSTICK.get_axis(3) if JOYSTICK.get_numaxes() > 3 else 0.0

            # Normalisation linéaire
            forward = normalize_axis(-y_axis, 0.3)
            turn = normalize_axis(x_axis, 0.3)
            
            arm_v = normalize_axis(-arm_y, 0.2)
            arm_r = normalize_axis(arm_x, 0.2)

            # Envoi des commandes analogiques
            if control_state.mode_index == 2:
                send_analog_drive(forward, turn)
                drive_arm_analog(arm_v, arm_r)

                # D-Pad (Hat) -> Contrôle de la MAIN (Servo 3)
                hat_x, hat_y = safe_get_hat(JOYSTICK)
                
                if hat_y == 1:
                    send_command("handup")
                elif hat_y == -1:
                    send_command("handdown")
                else:
                    send_command("HAstop")

                # Calibration (Gauche/Droite sur D-Pad)
                if hat_x == -1:
                    send_command("cali_left")
                elif hat_x == 1:
                    send_command("cali_right")

            # Boutons (Mapping PS4/Xbox standard)
            # 0: A/Croix, 1: B/Rond, 2: X/Carré, 3: Y/Triangle
            if JOYSTICK.get_numbuttons() >= 4:
                b0 = JOYSTICK.get_button(0) # A / Croix
                b1 = JOYSTICK.get_button(1) # B / Rond
                b2 = JOYSTICK.get_button(2) # X / Carré
                b3 = JOYSTICK.get_button(3) # Y / Triangle

                # Mode Police (Croix / A)
                if b0 and not last_button_states.get("button_0"):
                    toggle_mode("police")
                last_button_states["button_0"] = b0

                # Mode R2-D2 (Rond / B)
                if b1 and not last_button_states.get("button_1"):
                    toggle_mode("r2d2")
                last_button_states["button_1"] = b1

                # Mode Disco (Carré / X)
                if b2 and not last_button_states.get("button_2"):
                    toggle_mode("disco")
                last_button_states["button_2"] = b2

                # Arrêt d'Urgence (Triangle / Y)
                if b3:
                    emergency_stop()

            # Modes Autonomes (Mapping L1 / R1)
            if JOYSTICK.get_numbuttons() >= 6:
                l1 = JOYSTICK.get_button(4) # L1
                r1 = JOYSTICK.get_button(5) # R1
                
                if l1 and not last_button_states.get("button_4"):
                    toggle_mode("trackLine")
                last_button_states["button_4"] = l1
                
                if r1 and not last_button_states.get("button_5"):
                    toggle_mode("automatic")
                last_button_states["button_5"] = r1

            # Mode findColor (Mapping L3 ou R3 si dispo)
            if JOYSTICK.get_numbuttons() >= 10:
                l3 = JOYSTICK.get_button(8) # L3
                if l3 and not last_button_states.get("button_8"):
                    toggle_mode("findColor")
                last_button_states["button_8"] = l3

            # Gâchettes (L2/R2) pour Pince (Ouvrir/Fermer)
            if JOYSTICK.get_numbuttons() >= 8:
                l2 = JOYSTICK.get_button(6) # L2
                r2 = JOYSTICK.get_button(7) # R2
                
                current_grip = "stop"
                if l2:
                    current_grip = "loose"
                elif r2:
                    current_grip = "grab"
                
                if current_grip != last_grip_state:
                    if current_grip == "loose":
                        send_command("loose")
                    elif current_grip == "grab":
                        send_command("grab")
                    else:
                        send_command("gripStop")
                    last_grip_state = current_grip

        except Exception as exc:
            append_log(f"Erreur joystick loop: {exc}")

        time.sleep(0.03)

# -----------------------------------------------------
# UTILS (radar_view stub for legacy GUI compatibility)
# -----------------------------------------------------

def radar_view(x, y, info):
    """
    Provided as a compatibility hook for old GUI code which may call radar_view.
    The real GUI will implement the visual. Here we log only.
    """
    append_log(f"Radar data reçu ({len(info)} points)")

# End of client_core.py
