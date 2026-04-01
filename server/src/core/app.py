#!/usr/bin/env/python
# File name   : app.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date		  : 2025/03/25
from importlib import import_module
import os
from flask import Flask, render_template, Response, send_from_directory
from flask_cors import *

from camera_opencv import Camera
import threading

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Global state for camera on-demand
camera = None
client_count = 0
camera_lock = threading.Lock()

def get_camera():
    global camera
    if camera is None:
        camera = Camera()
    return camera

def gen(camera_func):
    global client_count, camera
    
    with camera_lock:
        client_count += 1
        print(f"[app] Client connected. Count: {client_count}")
        if client_count == 1:
            # First client, start camera
            print("[app] Starting camera...")
            get_camera()

    try:
        # Use the global camera instance
        cam = get_camera()
        while True:
            frame = cam.get_frame()
            if frame is None:
                break
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    except Exception as e:
        print(f"[app] Stream error: {e}")
    finally:
        with camera_lock:
            client_count -= 1
            print(f"[app] Client disconnected. Count: {client_count}")
            if client_count == 0:
                print("[app] Stopping camera...")
                if camera:
                    camera.stop_thread() # Stop the BaseCamera thread
                    camera = None

@app.route('/video_feed')
def video_feed():
    return Response(gen(None),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

dir_path = os.path.dirname(os.path.realpath(__file__))

@app.route('/api/img/<path:filename>')
def sendimg(filename):
    return send_from_directory(dir_path+'/dist/img', filename)

@app.route('/js/<path:filename>')
def sendjs(filename):
    return send_from_directory(dir_path+'/dist/js', filename)

@app.route('/css/<path:filename>')
def sendcss(filename):
    return send_from_directory(dir_path+'/dist/css', filename)

@app.route('/api/img/icon/<path:filename>')
def sendicon(filename):
    return send_from_directory(dir_path+'/dist/img/icon', filename)

@app.route('/fonts/<path:filename>')
def sendfonts(filename):
    return send_from_directory(dir_path+'/dist/fonts', filename)

@app.route('/<path:filename>')
def sendgen(filename):
    return send_from_directory(dir_path+'/dist', filename)

@app.route('/ui')
def ui():
    return send_from_directory(dir_path+'/dist', 'index.html')

@app.route('/')
def index():
    return send_from_directory(dir_path, 'video.html')

class webapp:
    def __init__(self):
        pass

    def modeselect(self, modeInput):
        Camera.modeSelect = modeInput

    def colorFindSet(self, H, S, V):
        # We need to be careful here. If camera is not running, we can't set color.
        # But Camera class methods might be static or class level?
        # Looking at camera_opencv.py, colorFindSet is an instance method.
        # But it modifies global variables in camera_opencv.py.
        # So we can create a temporary instance or just rely on the fact that
        # if we are setting color, we probably have the camera running.
        # For safety, we check if camera exists.
        global camera
        if camera:
            camera.colorFindSet(H, S, V)

    def thread(self):
        app.run(host='0.0.0.0', port=5000, threaded=True)

    def startthread(self):
        fps_threading=threading.Thread(target=self.thread)             
        fps_threading.daemon = False
        fps_threading.start()           


if __name__ == "__main__":
    WEB = webapp()
    try:
        WEB.startthread()
        # WEB.modeselect('findColor') # Don't start CV mode by default
    except:
        print("exit")
