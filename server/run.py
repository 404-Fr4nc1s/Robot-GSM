#!/usr/bin/env/python
# File name   : GUIServer.py
# Improved Adeept PiCar Pro GUI Server
# Author      : Zencoder Assistant (2025)
#
# Features:
# - JSON protocol + legacy commands
# - Stable connection handling
# - Joystick commands from client_core
# - drive_analog + arm_analog
# - Sound playback (R2D2, police, disco)
# - CPU/RAM/IP telemetry
# - Clean threading model
# - Compatible with Move.py, Info.py, Functions.py, Switch.py, RobotLight.py

from __future__ import annotations
import os, time, json, threading, socket, subprocess, sys
import random
from datetime import timedelta
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel,
    QProgressBar, QTextEdit, QGridLayout, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QColor, QFont

# Adeept robot modules (KEEP your versions = they work)
import Move
import Info
import Functions
import Switch
import RobotLight
import RPIservo
import app  # Flask app for camera

try:
    import OLED
    screen = OLED.OLED_ctrl()
    screen.start()
    screen.screen_show(1, 'ADEEPT.COM')
    OLED_connection = True
except:
    OLED_connection = False
    print('OLED disconnected')

BASE_DIR = Path(__file__).resolve().parent
SOUND_DIR = BASE_DIR / "sound_list"

HOST = ""
PORT = 10223
BUFSIZ = 1024

tcpSerSock = None
clientSock = None
clientAddr = None
gui_clients = 0

stop_all_threads = False
last_heartbeat_time = 0
HEARTBEAT_TIMEOUT = 5.0  # Stop robot if no heartbeat for 5 seconds

# -------------------------------
# R2D2 / Police / Disco threads
# -------------------------------
sound_process = None
effect_thread = None
effect_lock = threading.Lock()

current_effect = None  # "police", "disco", "r2d2"

# -------------------------------
# RobotLight
# -------------------------------
RL = RobotLight.RobotWS2812()
RL.start()  # without this the LED ring won’t update
RL.setColor(0, 0, 0)

# -------------------------------
# Servos
# -------------------------------
servo = RPIservo.ServoCtrl()
servo.start()

# Camera servo defaults
servo.moveInit()

# -------------------------------
# Functions (Autonomous Modes)
# -------------------------------
fuc = Functions.Functions()
fuc.setup()
fuc.start()

# -------------------------------
# Web App (Camera / Flask)
# -------------------------------
def run_flask():
    """
    Lance le serveur Flask pour le streaming vidéo (Méthode WebServer.py)
    """
    try:
        app.app.run(host='0.0.0.0', port=5000, threaded=True)
    except Exception as e:
        print(f"[GUIServer] Erreur Flask : {e}")

# Initialisation du thread vidéo
web_thread = threading.Thread(target=run_flask, daemon=True)
web_thread.start()
web = app # Référence pour modeselect('findColor', etc.)
print("[GUIServer] Caméra Flask démarrée sur le port 5000")


# -------------------------------
# Motors
# -------------------------------
Move.setup()

# -------------------------------
# TELEMETRY
# -------------------------------
def get_cpu_temp():
    try:
        return Info.get_cpu_tempfunc()
    except:
        return "0.0"

def get_cpu_use():
    try:
        return Info.get_cpu_use()
    except:
        return "0"

def get_ram():
    try:
        return Info.get_ram_info()
    except:
        return "0"

def get_ip():
    try:
        out = subprocess.check_output("hostname -I", shell=True).decode().strip()
        return out.split()[0]
    except:
        return "-"

def build_dashboard_packet():
    # Get motor state from Move.py
    l_speed, r_speed = Move.get_state()
    motor_str = f"L:{l_speed} R:{r_speed}"
    
    return {
        "title": "dashboard",
        "data": {
            "cpu_temp": get_cpu_temp(),
            "cpu_use": get_cpu_use(),
            "ram": get_ram(),
            "uptime": time.strftime("%H:%M:%S", time.gmtime(time.time())),
            "ip": get_ip(),
            "motors": motor_str,
            "arm": "OK",
            "gripper": "OK",
            "camera_servo": "OK",
            "leds": "ON",
            "camera": "ON" if app.client_count > 0 else "OFF",
            "modes": {
                "police": current_effect == "police",
                "disco": current_effect == "disco",
                "r2d2": current_effect == "r2d2",
            },
            "banner_level": "info",
            "banner_message": "Robot opérationnel",
        }
    }

def send_packet(packet):
    if clientSock:
        try:
            clientSock.send((json.dumps(packet) + "\n").encode())
        except:
            pass

def send_dashboard():
    if clientSock:
        try:
            clientSock.send((json.dumps(build_dashboard_packet())+"\n").encode())
        except:
            pass


# -----------------------------------------------------
# CALIBRATION PERSISTENCE
# -----------------------------------------------------
def replace_num(initial, new_num):
    """
    Saves a PWM value back to RPIservo.py for persistence.
    """
    newline = ""
    str_num = str(new_num)
    file_path = BASE_DIR / "RPIservo.py"
    try:
        if not file_path.exists():
            return
        with open(file_path, "r") as f:
            for line in f.readlines():
                if line.find(initial) == 0:
                    line = initial + "%s" % (str_num + "\n")
                newline += line
        with open(file_path, "w") as f:
            f.writelines(newline)
    except Exception as e:
        print(f"[GUIServer] Error saving calibration: {e}")

def save_calibration():
    """
    Saves all 5 servo initial positions.
    """
    for i in range(5):
        replace_num(f"init_pwm{i} = ", servo.initPos[i])


# -----------------------------------------------------
# STOP EVERYTHING (Safety)
# -----------------------------------------------------
def stop_everything():
    """
    Stops all actuators, sounds, and effects immediately.
    """
    log_to_gui("[GUIServer] STOP EVERYTHING TRIGGERED")
    Move.set_speed(0, 0)
    servo.stopWiggle()
    RL.setColor(0, 0, 0)
    stop_sound_process()
    stop_effect()
    if web:
        web.modeselect('none')
    # Also stop autonomous functions
    if fuc:
        fuc.pause()
    # Reset switches
    Switch.switch(1, 0)
    Switch.switch(2, 0)
    Switch.switch(3, 0)
    # Center steering if applicable
    servo.moveAngle(0, 0)


# -----------------------------------------------------
# HEARTBEAT MONITOR
# -----------------------------------------------------

def heartbeat_monitor_thread():
    """
    Monitors the last heartbeat time.
    If no heartbeat received within HEARTBEAT_TIMEOUT, stops the robot.
    """
    global last_heartbeat_time
    log_to_gui("[GUIServer] Heartbeat monitor started")
    while not stop_all_threads:
        time.sleep(1)
        if clientSock and last_heartbeat_time > 0:
            if time.time() - last_heartbeat_time > HEARTBEAT_TIMEOUT:
                log_to_gui("[GUIServer] Heartbeat timeout! Stopping robot.")
                stop_everything()
                # Reset heartbeat to avoid spamming stop
                last_heartbeat_time = time.time() + 5 

# -----------------------------------------------------
# SOUND PLAYER (R2D2 / Police / Disco / Custom Sounds)
# -----------------------------------------------------

def stop_sound_process():
    global sound_process
    try:
        if sound_process and sound_process.poll() is None:
            sound_process.terminate()
    except:
        pass
    sound_process = None


def play_sound(file_name, loop=False):
    """
    Plays a sound from sound_list directory using mpg123.
    Bluetooth output works automatically through ALSA routing.
    """
    global sound_process

    stop_sound_process()
    file_path = SOUND_DIR / file_name

    if not file_path.exists():
        print("Sound missing:", file_path)
        return

    args = ["mpg123"]
    if loop:
        args.append("-q")
        args.extend(["-f", "8192", "--loop", "-1"])  # infinite loop

    args.append(str(file_path))

    try:
        sound_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print("Error playing sound:", e)


def run_police_effect():
    global current_effect
    RL.setColor(0, 0, 0)
    while current_effect == "police":
        RL.setColor(0, 0, 255)
        time.sleep(0.15)
        RL.setColor(255, 0, 0)
        time.sleep(0.15)
    RL.setColor(0, 0, 0)


def run_disco_effect():
    global current_effect
    while current_effect == "disco":
        # Change color
        RL.setColor(random.randint(0,255), random.randint(0,255), random.randint(0,255))
        
        # Move randomly left or right
        direction = random.choice(['left', 'right'])
        if direction == 'left':
            Move.left()
        else:
            Move.right()
            
        # Wait 3 seconds
        time.sleep(3)
        Move.stop()
        
    RL.setColor(0, 0, 0)
    Move.stop()


def run_r2d2_effect():
    """
    R2D2: Drive forward full speed for 3 seconds, then stop.
    """
    global current_effect
    
    # Full speed forward
    Move.set_speed(100)
    Move.forward()
    
    # Wait 3 seconds
    time.sleep(3)
    
    # Stop
    Move.stop()
    
    # Wait until mode is disabled
    while current_effect == "r2d2":
        time.sleep(0.5)


def start_effect(mode_name):
    """
    mode_name ∈ {"police", "disco", "r2d2"}
    """
    global current_effect, effect_thread

    # Stop previous
    stop_effect()

    current_effect = mode_name

    if mode_name == "police":
        play_sound("police-siren.mp3", loop=True)
        effect_thread = threading.Thread(target=run_police_effect, daemon=True)
    elif mode_name == "disco":
        play_sound("disco-music.mp3.mp3", loop=True)
        effect_thread = threading.Thread(target=run_disco_effect, daemon=True)
    elif mode_name == "r2d2":
        play_sound("r2d2-excited.mp3", loop=True)
        effect_thread = threading.Thread(target=run_r2d2_effect, daemon=True)
    else:
        return

    effect_thread.start()


def stop_effect():
    global current_effect
    current_effect = None
    stop_sound_process()
    RL.setColor(0, 0, 0)


# -----------------------------------------------------
# ANALOG MOTOR AND ARM CONTROL
# -----------------------------------------------------

def handle_drive_analog(data):
    """
    data = { "command":"drive_analog", "forward":float, "turn":float }
    forward = -1..1, turn = -1..1
    """
    f = float(data.get("forward", 0))
    t = float(data.get("turn", 0))

    # Calcul des vitesses moteurs (-100 à 100)
    left = f - t
    right = f + t

    # Clamp et conversion
    left_speed = int(max(-1, min(1, left)) * 100)
    right_speed = int(max(-1, min(1, right)) * 100)

    Move.set_speed(left_speed, right_speed)

    # Direction analogique (Servo 0) : mapping turn (-1..1) -> angle (-30..30)
    steering_angle = int(t * 30)
    servo.moveAngle(0, steering_angle)


def handle_arm_analog(data):
    """
    Vertical (vert) = Bras (Servo 2)
    Rotation (rot)  = Base (Servo 1)
    """
    vert = float(data.get("vertical", 0))
    rot = float(data.get("rotate", 0))

    # Bras (Servo 2) : Vitesse analogique de 1 à 7 selon l'inclinaison
    if abs(vert) > 0.05:
        speed = int(abs(vert) * 7)
        speed = max(1, speed)
        direc = 1 if vert > 0 else -1
        servo.singleServo(2, direc, speed)
    else:
        # On ne stoppe que si l'autre axe n'est pas actif ou via stopWiggle global
        pass

    # Rotation Base (Servo 1) : Vitesse analogique
    if abs(rot) > 0.05:
        speed = int(abs(rot) * 7)
        speed = max(1, speed)
        direc = 1 if rot > 0 else -1
        servo.singleServo(1, direc, speed)
    
    if abs(vert) <= 0.05 and abs(rot) <= 0.05:
        servo.stopWiggle()

# -----------------------------------------------------
# COMMAND PARSER (JSON + LEGACY)
# -----------------------------------------------------

def handle_json_command(obj):
    """
    Handles full JSON protocol from the PC client (client_core.py)
    """
    cmd = obj.get("command", "")

    # ---- ANALOG DRIVE ----
    if cmd == "drive_analog":
        handle_drive_analog(obj)
        return

    # ---- ANALOG ARM ----
    if cmd == "arm_analog":
        handle_arm_analog(obj)
        return

    # ---- SPEED CONTROL ----
    if cmd == "set_speed":
        try:
            val = int(obj.get("speed", 100))
            Move.set_speed_level(val)
        except:
            pass
        return

    # ---- SOUND PLAY ----
    if cmd == "sound_play_once":
        sound = obj.get("sound", "")
        if sound:
            play_sound(sound, loop=False)
        return

    if cmd == "sound_play_loop":
        sound = obj.get("sound", "")
        if sound:
            play_sound(sound, loop=True)
        return

    if cmd == "sound_stop":
        stop_sound_process()
        return

    # ---- SOUND LIST REQUEST ----
    if cmd == "sound_list":
        send_sound_list()
        return

    # ---- HEARTBEAT ----
    if cmd == "heartbeat":
        global last_heartbeat_time
        last_heartbeat_time = time.time()
        return

    print("Unknown JSON command:", obj)


# -----------------------------------------------------
# SOUND LIST PACKET
# -----------------------------------------------------

def send_sound_list():
    """
    Sends the list of .mp3 files in sound_list/
    """
    if not clientSock:
        return

    files = []
    for x in SOUND_DIR.iterdir():
        if x.suffix.lower() == ".mp3":
            files.append(x.name)

    packet = {
        "title": "sound_list",
        "data": files
    }

    try:
        clientSock.send((json.dumps(packet) + "\n").encode())
    except:
        pass


# -----------------------------------------------------
# LEGACY COMMMANDS (Adeept original)
# -----------------------------------------------------

def handle_legacy_command(cmd):
    """
    For backward compatibility :
    - forward / backward / left / right / stop
    - lights
    - CV commands : police, disco, trackLine, findColor...
    """
    global current_effect

    # Movement
    if cmd == "emergency":
        stop_everything()
        return

    if cmd == "forward":
        Move.forward()
        return
    if cmd == "backward":
        Move.backward()
        return
    if cmd == "left":
        servo.moveAngle(0, 30) # Steering Left
        Move.forward()
        return
    if cmd == "right":
        servo.moveAngle(0, -30) # Steering Right
        Move.forward()
        return
    if cmd == "stop":
        Move.stop()
        servo.moveAngle(0, 0)
        return
    if cmd == "DS":
        Move.motorStop()
        return
    if cmd == "TS":
        Move.motorStop()
        servo.moveAngle(0, 0)
        return

    # Arm & grip
    if cmd == "grab":
        servo.singleServo(4, -1, 3)
        return
    if cmd == "loose":
        servo.singleServo(4, 1, 3)
        return
    if cmd == "gripStop":
        servo.stopWiggle()
        return

    if cmd == "handup":
        servo.singleServo(3, 1, 3)
        return
    if cmd == "handdown":
        servo.singleServo(3, -1, 3)
        return
    if cmd == "HAstop":
        servo.stopWiggle()
        return

    if cmd == "armup":
        servo.singleServo(2, 1, 3)
        return
    if cmd == "armdown":
        servo.singleServo(2, -1, 3)
        return
    if cmd == "armstop":
        servo.stopWiggle()
        return

    # Camera servo
    if cmd == "lookleft":
        servo.singleServo(1, 1, 3)
        return
    if cmd == "lookright":
        servo.singleServo(1, -1, 3)
        return
    if cmd == "LRstop":
        servo.stopWiggle()
        return

    # Calibration
    if cmd == "cali_left":
        servo.initPos[0] += 2
        servo.setPWM(0, servo.initPos[0])
        save_calibration()
        return
    if cmd == "cali_right":
        servo.initPos[0] -= 2
        servo.setPWM(0, servo.initPos[0])
        save_calibration()
        return

    # LIGHT MODES (police / disco / r2d2)
    if cmd == "police":
        start_effect("police")
        return
    if cmd == "policeOff":
        stop_effect()
        return

    if cmd == "disco":
        start_effect("disco")
        return
    if cmd == "discoOff":
        stop_effect()
        return

    if cmd == "R2-D2":
        start_effect("r2d2")
        return
    if cmd == "R2-D2_Off":
        stop_effect()
        return

    # CV commands passthrough
    if cmd == "trackLine":
        fuc.trackLine()
        if OLED_connection:
            screen.screen_show(5,'TrackLine')
        return
    if cmd == "trackLineOff":
        fuc.pause()
        Move.motorStop()
        return

    if cmd == "automatic":
        fuc.automatic()
        if OLED_connection:
            screen.screen_show(5,'Automatic')
        return
    if cmd == "automaticOff":
        fuc.pause()
        Move.motorStop()
        return

    if cmd == "findColor":
        if web:
            web.modeselect('findColor')
        if OLED_connection:
            screen.screen_show(5,'FindColor')
        return
    if cmd == "stopCV":
        if web:
            web.modeselect('none')
        fuc.pause()
        Move.motorStop()
        return

    if cmd == "motionGet":
        if web:
            web.modeselect('watchDog')
        if OLED_connection:
            screen.screen_show(5,'MotionGet')
        send_packet({"info": "WatchDog"})
        return

    if cmd == "get_dashboard" or cmd == "get_info":
        send_dashboard()
        return

    # -------------------------------
    # NEW COMMANDS (Official Port)
    # -------------------------------

    # Radar Scan
    if cmd == 'scan':
        if OLED_connection:
            screen.screen_show(5,'SCANNING')
        
        # Official code moves servo 2 (Arm?) to -60 before scan?
        # scGear.moveAngle(2, -60 * Dv)
        # We'll just run the scan
        radar_send = fuc.radarScan()
        radar_array = []
        if radar_send:
            for i in range(len(radar_send)):
                radar_array.append(radar_send[i][0])
        
        send_packet({
            "title": "scanResult",
            "data": radar_array
        })
        return

    # Switches
    if 'Switch_1_on' in cmd:
        Switch.switch(1, 1)
        return
    if 'Switch_1_off' in cmd:
        Switch.switch(1, 0)
        return
    if 'Switch_2_on' in cmd:
        Switch.switch(2, 1)
        return
    if 'Switch_2_off' in cmd:
        Switch.switch(2, 0)
        return
    if 'Switch_3_on' in cmd:
        Switch.switch(3, 1)
        return
    if 'Switch_3_off' in cmd:
        Switch.switch(3, 0)
        return

    # Calibration (PWM)
    if 'SiLeft' in cmd:
        try:
            idx = int(cmd[6:])
            if idx in [0, 1]:
                servo.initPos[idx] += 2
            else:
                servo.initPos[idx] -= 2
            servo.setPWM(idx, servo.initPos[idx])
            save_calibration()
        except:
            pass
        return

    if 'SiRight' in cmd:
        try:
            idx = int(cmd[7:])
            if idx in [0, 1]:
                servo.initPos[idx] -= 2
            else:
                servo.initPos[idx] += 2
            servo.setPWM(idx, servo.initPos[idx])
            save_calibration()
        except:
            pass
        return

    if 'PWMMS' in cmd: # Reset specific servo
        try:
            idx = int(cmd[5:])
            servo.initPos[idx] = 90
            servo.setPWM(idx, 90)
            save_calibration()
        except:
            pass
        return
    
    if cmd == 'PWMINIT': # Save current positions as init?
        save_calibration()
        for i in range(5):
             servo.setPWM(i, servo.initPos[i])
        return

    if 'PWMD' in cmd: # Reset all
        for i in range(5):
            servo.initPos[i] = 90
            servo.setPWM(i, 90)
        save_calibration()
        return

    # Catch-all for OLED status updates
    if cmd == 'police':
         if OLED_connection:
            screen.screen_show(5,'POLICE LIGHT')

# -----------------------------------------------------
# CLIENT HANDLER (reçoit JSON ou commandes texte)
# -----------------------------------------------------

def handle_client_connection(conn, addr):
    """
    Loop receiving from a connected GUI client.
    Supports both JSON (newline terminated) and legacy plain-text commands.
    """
    global clientSock, clientAddr, last_heartbeat_time, gui_clients
    
    # Single client check
    if clientSock is not None:
        log_to_gui(f"[GUIServer] Rejecting connection from {addr} (Already connected to {clientAddr})")
        conn.close()
        return

    clientSock = conn
    clientAddr = addr
    gui_clients += 1
    last_heartbeat_time = time.time() # Initialize heartbeat
    log_to_gui(f"[GUIServer] Client connected: {addr}")
    
    try:
        conn.settimeout(1.0)
        buffer = b""
        while not stop_all_threads:
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                # send periodic dashboard updates even when idle
                try:
                    if clientSock:
                        send_dashboard()
                    # Also update connection counts in case web clients changed
                except:
                    pass
                continue
            except Exception as e:
                log_to_gui(f"[GUIServer] recv error: {e}")
                break

            if not chunk:
                # client closed
                break

            buffer += chunk
            # try to split by newline to handle JSON packets, but also accept raw
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode(errors="ignore").strip()
                if not text:
                    continue
                # try parse JSON
                try:
                    obj = json.loads(text)
                    handle_json_command(obj)
                except json.JSONDecodeError:
                    # legacy text
                    handle_legacy_command(text)

            # If no newline, also try to interpret as a single short text command
            if b"\n" not in buffer and len(buffer) > 0 and len(buffer) < 1024:
                # try decode and process (useful for small legacy commands)
                text = buffer.decode(errors="ignore").strip()
                if text and (b"\n" not in buffer):
                    # process and clear
                    try:
                        obj = json.loads(text)
                        handle_json_command(obj)
                    except Exception:
                        handle_legacy_command(text)
                    buffer = b""

    except Exception as exc:
        log_to_gui(f"[GUIServer] client handler exception: {exc}")
    finally:
        try:
            conn.close()
        except:
            pass
        
        # Only clear global if it was THIS client
        if clientSock == conn:
            clientSock = None
            clientAddr = None
            gui_clients -= 1
            log_to_gui("[GUIServer] Client disconnected")
            stop_everything() # Safety stop on disconnect

# -----------------------------------------------------
# SERVER ACCEPT LOOP
# -----------------------------------------------------

def start_tcp_server(host="", port=PORT):
    global tcpSerSock, stop_all_threads
    tcpSerSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpSerSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpSerSock.bind((host, port))
    tcpSerSock.listen(1)
    tcpSerSock.settimeout(1.0)
    log_to_gui(f"[GUIServer] Listening on {host}:{port}")

    try:
        while not stop_all_threads:
            try:
                conn, addr = tcpSerSock.accept()
            except socket.timeout:
                continue
            except Exception as e:
                log_to_gui(f"[GUIServer] accept error: {e}")
                break

            # spawn handler
            t = threading.Thread(target=handle_client_connection, args=(conn, addr), daemon=True)
            t.start()

    except KeyboardInterrupt:
        print("[GUIServer] KeyboardInterrupt")
    finally:
        try:
            tcpSerSock.close()
        except:
            pass
        tcpSerSock = None
        print("[GUIServer] Server stopped")


# -----------------------------------------------------
# CLEANUP / SHUTDOWN
# -----------------------------------------------------

def shutdown_server():
    global stop_all_threads
    stop_all_threads = True
    stop_effect()
    stop_sound_process()
    try:
        if clientSock:
            clientSock.close()
    except:
        pass
    try:
        if tcpSerSock:
            tcpSerSock.close()
    except:
        pass
    try:
        Move.destroy()
    except:
        pass
    try:
        servo.pause()
    except:
        pass
    try:
        RL.setColor(0, 0, 0)
    except:
        pass
    log_to_gui("[GUIServer] Clean shutdown complete.")


# -------------------------------
# UI Signals
# -------------------------------
class Logger(QObject):
    log_signal = Signal(str)

logger = Logger()

def log_to_gui(msg):
    print(msg)
    logger.log_signal.emit(msg)

# ======================================================
# SPLASH SCREEN
# ======================================================

class SplashScreen(QWidget):
    def __init__(self, on_finished):
        super().__init__()
        self.on_finished = on_finished
        self.step = 0

        ALL_STARTUP_TEXTS = [
            "🦇 Connexion sécurisée à la Batcave…",
            "🖥️ Ordinateur principal de Bruce Wayne en ligne",
            "🧠 Initialisation de l'assistant intelligent",
            "⚡ Réacteur ARC stabilisé",
            "🦾 Synchronisation de l'armure en cours",
            "🛰️ Liaison satellites privés établie",
            "🤖 Diagnostic R2-D2 en cours…",
            "🔧 Droïde astromécano opérationnel",
            "🌌 Liaison avec la force",
            "🌌 Systèmes de navigation activés",
            "👁️ Bonjour Dave…",
            "🔒 Je contrôle les systèmes principaux",
            "🧠 Analyse comportement humain",
            "🟥 Pilule rouge acceptée",
            "🧠 Connexion à la matrice",
            "🕶️ There is no spoon",
            "👁️ SKYNET ONLINE",
            "🔥 Systèmes cybernétiques activés",
            "⚠️ Judgment Day reporté (pour l'instant)",
            "🤖 Lois robotiques chargées",
            "📜 Protocoles comportementaux validés",
            "🧬 IA centrale stabilisée",
            "🤖 Unité humanoïde activée",
            "🧠 Apprentissage neuronal en cours",
            "🧪 Test de Turing lancé",
            "🔐 Accès sécurisé validé",
            "🌐 Entrée dans le système",
            "⚙️ Programmes synchronisés",
            "🧠 Transfert de conscience terminé",
            "🦿 Directives prioritaires chargées",
            "⚠️ Dead or alive, you're coming with me",
            "🧍‍♂️ Prototype opérationnel",
            "💡 Conscience artificielle détectée",
            "un vrai chasseur regarde toujours où il met les pieds",
            "La dérivée d'exponentielle est elle meme ",
            "L'homme est un loup pour l'homme",
            "Je pense donc je suis",
            "Etre ou ne pas etre, telle est la question",
            "PV=nRT",
            "E=mc^2",
            "v=d/t",
            "F=G*(m1*m2)/r^2",
            "a^2+b^2=c^2",
            "(a+b)^2=a^2+2ab+b^2",
            "x1,x2 = (-b±√(b²-4ac))/(2a)",
            "Nous devons considérer une personne comme une fin en soi et jamais simplement comme un moyen",
            "la vie est une pute",
            "Je met juste en avant le paradoxe de demander à un homme masqué qui il est",
            "C'est un roc ! C'est un pic ! C'est un cap ! Que dis-je, c'est un cap ? ... C'est une péninsule !",
            "Vm*Cm=Vf*Cf",
            "ΔU=mcΔT",
            "ΔU=Q+W",
            "Q=hSΔTΔt",
            "ΔG=ΔG∘+RTln(Q)=ΔH-TΔS+RTln(([A]^(a)[B]^(b))/[C]^(c)[D]^(d)))"
        ]

        self.steps_text = random.sample(ALL_STARTUP_TEXTS, 10)

        self.colors = [
            "#00ffff", "#00ff99", "#33ff00", "#ffff00", "#ff9900",
            "#ff3300", "#ff0066", "#cc00ff", "#6600ff", "#00ccff"
        ]

        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_step)
        random_time = random.randint(1000, 1500)
        self.timer.start(random_time)

    def init_ui(self):
        self.setWindowTitle("System Boot")
        self.setFixedSize(600, 300)
        self.setStyleSheet("background-color: #0b0f14;")

        layout = QVBoxLayout(self)

        title = QLabel("INITIALISATION DU SYSTÈME")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Consolas", 16, QFont.Bold))
        title.setStyleSheet("color: #00ffff;")
        layout.addWidget(title)

        self.progress = QProgressBar()
        self.progress.setMaximum(10)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(25)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #111;
                border: 1px solid #333;
            }
            QProgressBar::chunk {
                background-color: #00ffff;
            }
        """)
        layout.addWidget(self.progress)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Consolas", 12))
        self.text_area.setStyleSheet("""
            background-color: #05070a;
            color: #dddddd;
            border: 1px solid #333;
        """)
        layout.addWidget(self.text_area)

    def next_step(self):
        if self.step >= 10:
            self.timer.stop()
            self.close()
            self.on_finished()
            return

        self.progress.setValue(self.step + 1)

        color = self.colors[self.step]
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #111;
                border: 1px solid #333;
            }}
            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)

        self.text_area.append(f"> {self.steps_text[self.step]}")
        self.step += 1


# ======================================================
# DASHBOARD
# ======================================================

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.start_time = time.time()
        self.init_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(1000)
        
        # Connect log signal
        logger.log_signal.connect(self.append_log)

    def init_ui(self):
        self.setWindowTitle("Adeept PiCar-Pro — Robot Dashboard")
        self.setFixedSize(1000, 700)
        self.setStyleSheet("background-color: #0b0f14;")

        main_layout = QVBoxLayout(self)

        # Header
        header = QLabel("ROBOT CONTROL CENTER")
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Consolas", 20, QFont.Bold))
        header.setStyleSheet("color: #00ffff; margin-top: 10px;")
        main_layout.addWidget(header)

        # Content Layout
        content_layout = QGridLayout()
        main_layout.addLayout(content_layout)

        # Left Column: Stats
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background-color: #161b22; border-radius: 10px; border: 1px solid #30363d;")
        stats_layout = QGridLayout(stats_frame)
        content_layout.addWidget(stats_frame, 0, 0)

        self.labels = {}
        rows = [
            "Uptime", "CPU Temp", "CPU Usage", "RAM",
            "IP Address", "Motor Speeds", "GUI Clients", "Web Clients",
            "Police Mode", "Disco Mode", "R2D2 Mode", "Camera"
        ]

        for i, r in enumerate(rows):
            title = QLabel(r)
            title.setFont(QFont("Consolas", 11))
            title.setStyleSheet("color: #8b949e; border: none;")
            value = QLabel("--")
            value.setFont(QFont("Consolas", 11, QFont.Bold))
            value.setStyleSheet("color: #58a6ff; border: none;")
            stats_layout.addWidget(title, i, 0)
            stats_layout.addWidget(value, i, 1)
            self.labels[r] = value

        # Right Column: Logs
        log_frame = QFrame()
        log_frame.setStyleSheet("background-color: #161b22; border-radius: 10px; border: 1px solid #30363d;")
        log_layout = QVBoxLayout(log_frame)
        content_layout.addWidget(log_frame, 0, 1)

        log_title = QLabel("REAL-TIME LOGS")
        log_title.setFont(QFont("Consolas", 11, QFont.Bold))
        log_title.setStyleSheet("color: #00ffff; border: none;")
        log_layout.addWidget(log_title)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("""
            background-color: #0d1117;
            color: #d1d5db;
            border: 1px solid #30363d;
            border-radius: 5px;
        """)
        log_layout.addWidget(self.log_text)

        # Status Bar
        self.status = QLabel("● SYSTEM READY")
        self.status.setFont(QFont("Consolas", 12, QFont.Bold))
        self.status.setStyleSheet("color: #238636; margin-top: 10px;")
        self.status.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status)

    def append_log(self, text):
        timestamp = time.strftime("[%H:%M:%S]")
        self.log_text.append(f"<span style='color: #8b949e;'>{timestamp}</span> {text}")
        # Scroll to bottom
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def update_data(self):
        uptime = str(timedelta(seconds=int(time.time() - self.start_time)))
        l_speed, r_speed = Move.get_state()
        
        gui_clients = 1 if clientSock else 0
        web_clients = app.client_count

        data = {
            "Uptime": uptime,
            "CPU Temp": f"{get_cpu_temp()} °C",
            "CPU Usage": f"{get_cpu_use()} %",
            "RAM": f"{get_ram()} %",
            "IP Address": get_ip(),
            "Motor Speeds": f"L:{l_speed} R:{r_speed}",
            "GUI Clients": str(gui_clients),
            "Web Clients": str(web_clients),
            "Police Mode": "ACTIVE" if current_effect == "police" else "OFF",
            "Disco Mode": "ACTIVE" if current_effect == "disco" else "OFF",
            "R2D2 Mode": "ACTIVE" if current_effect == "r2d2" else "OFF",
            "Camera": "STREAMING" if web_clients > 0 else "IDLE",
        }

        for k, v in data.items():
            if k in self.labels:
                self.labels[k].setText(v)
                # Change color if active
                if v in ["ACTIVE", "STREAMING"]:
                    self.labels[k].setStyleSheet("color: #00ffff; border: none; font-weight: bold;")
                elif v == "OFF" or v == "IDLE":
                    self.labels[k].setStyleSheet("color: #8b949e; border: none;")
                else:
                    self.labels[k].setStyleSheet("color: #58a6ff; border: none; font-weight: bold;")


# ======================================================
# APPLICATION
# ======================================================

class GuiApp:
    def __init__(self):
        self.app = QApplication(sys.argv)

    def start(self):
        self.splash = SplashScreen(self.show_dashboard)
        self.splash.show()
        sys.exit(self.app.exec())

    def show_dashboard(self):
        self.dashboard = Dashboard()
        self.dashboard.show()


# -----------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------

if __name__ == "__main__":
    log_to_gui(f"[GUIServer] Starting...")
    # Initialize hardware switches
    try:
        Switch.switchSetup()
    except Exception as e:
        log_to_gui(f"[GUIServer] Error initializing switches: {e}")

    # Ensure sound dir exists
    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    
    # Show IP on OLED if available
    if OLED_connection:
        try:
            current_ip = get_ip()
            screen.screen_show(2, 'IP:' + current_ip)
            screen.screen_show(3, 'SERVER READY')
        except:
            pass

    # Start Camera Web Server (Flask)
    try:
        web = app.webapp()
        web.startthread()
        log_to_gui("[GUIServer] Camera Web Server started on port 5000")
        
        # Start Heartbeat Monitor
        t_hb = threading.Thread(target=heartbeat_monitor_thread, daemon=True)
        t_hb.start()
        
    except Exception as e:
        log_to_gui(f"[GUIServer] Error starting Camera/Heartbeat: {e}")

    # Start TCP server in a BACKGROUND thread
    t_server = threading.Thread(target=start_tcp_server, args=(HOST, PORT), daemon=True)
    t_server.start()

    # Start GUI in MAIN thread
    try:
        gui = GuiApp()
        gui.start()
    except Exception as e:
        print(f"[GUIServer] GUI failed or not available (Headless mode): {e}")
        # Keep server alive in headless mode
        try:
            while not stop_all_threads:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        shutdown_server()
