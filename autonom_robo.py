from flask import Flask, request, jsonify
from flask_cors import CORS
import RPi.GPIO as GPIO
import time
import threading
import subprocess  # adÄugat pentru TTS

# ==== SETÄ‚RI ====
PORT_FLASK = 5001

# Senzori HC-SR04 (alege pinii tÄi)
SENSORS = {
    "front": {"trig": 23, "echo": 24},
    "left": {"trig": 17, "echo": 27},
    "right":  {"trig": 5,  "echo": 6}
}

# Motoare (exemplu L298N)
IN1, IN2 = 20, 21  # Motor stĂ˘nga
IN3, IN4 = 26, 19  # Motor dreapta

# Timp de miČ™care (ajusteazÄ dupÄ robotul tÄu!)
DURATION_FORWARD = 1.2   # secunde pentru mers Ă®nainte
DURATION_BACK    = 1.0   # secunde pentru mers Ă®napoi
DURATION_TURN    = 0.65  # secunde pentru rotire 90Â°

# Setup GPIO
GPIO.setmode(GPIO.BCM)
for key in SENSORS:
    GPIO.setup(SENSORS[key]["trig"], GPIO.OUT)
    GPIO.setup(SENSORS[key]["echo"], GPIO.IN)
for pin in [IN1, IN2, IN3, IN4]:
    GPIO.setup(pin, GPIO.OUT)

def get_distance(trig, echo):
    GPIO.output(trig, True)
    time.sleep(0.00001)
    GPIO.output(trig, False)
    start, stop = time.time(), time.time()
    timeout = start + 0.04
    while GPIO.input(echo) == 0 and time.time() < timeout:
        start = time.time()
    while GPIO.input(echo) == 1 and time.time() < timeout:
        stop = time.time()
    elapsed = stop - start
    distance = (elapsed * 34300) / 2
    return distance if distance < 400 else 400  # max 4m

def move_forward():
    GPIO.output(IN1, True)
    GPIO.output(IN2, False)
    GPIO.output(IN3, True)
    GPIO.output(IN4, False)

def move_right():
    GPIO.output(IN1, False)
    GPIO.output(IN2, True)
    GPIO.output(IN3, True)
    GPIO.output(IN4, False)

def move_left():
    GPIO.output(IN1, True)
    GPIO.output(IN2, False)
    GPIO.output(IN3, False)
    GPIO.output(IN4, True)

def move_backward():
    GPIO.output(IN1, False)
    GPIO.output(IN2, True)
    GPIO.output(IN3, False)
    GPIO.output(IN4, True)

def stop():
    for pin in [IN1, IN2, IN3, IN4]:
        GPIO.output(pin, False)

# === CONTROL MOD ===
current_mode    = "autonom"   # 'autonom' sau 'manual'
manual_command  = None        # Ultima comandÄ primitÄ
robot_running   = False
obstacle_thread = None        # thread de evitare

def obstacle_avoidance():
    global robot_running, current_mode, manual_command
    moving_forward = False
    while robot_running:
        if current_mode == "autonom":
            dist_f = get_distance(**SENSORS["front"])
            dist_l = get_distance(**SENSORS["left"])
            dist_r = get_distance(**SENSORS["right"])
            print(f"Autonom - Front: {dist_f:.1f}cm, Left: {dist_l:.1f}cm, Right: {dist_r:.1f}cm")
            if dist_f < 22:
                stop()
                moving_forward = False
                time.sleep(0.2)
                if dist_l > dist_r:
                    move_left()
                else:
                    move_right()
                time.sleep(DURATION_TURN)
                stop()
            else:
                if not moving_forward:
                    move_forward()
                    moving_forward = True
                time.sleep(0.05)
        elif current_mode == "manual":
            if manual_command:
                print(f"Execut comandÄ manualÄ: {manual_command}")
                if manual_command == "forward":
                    move_forward();   time.sleep(DURATION_FORWARD)
                elif manual_command == "back":
                    move_backward();  time.sleep(DURATION_BACK)
                elif manual_command == "left":
                    move_left();      time.sleep(DURATION_TURN)
                elif manual_command == "right":
                    move_right();     time.sleep(DURATION_TURN)
                elif manual_command == "stop":
                    stop()
                stop()
                manual_command = None
            else:
                stop()
            time.sleep(0.05)
        else:
            stop()
            time.sleep(0.1)
    stop()

# === Flask API ===
app = Flask(__name__)
CORS(app)

@app.route('/command', methods=['POST'])
def command():
    global current_mode, manual_command, robot_running, obstacle_thread
    data = request.json
    cmd  = data.get('command', '')
    print(f"Primit: {cmd}")

    if cmd.startswith("say:"):
        # extrage textul dupďż˝ "say:"
        text = cmd[len("say:"):].strip()
        # pipe espeak prin aplay, va folosi sink-ul default (bluetooth)
        subprocess.Popen(
            f'espeak -ven+f3 "{text}" --stdout | aplay',
            shell=True
        )
        return jsonify({"status": "ok", "msg": f"(voce) {text}"})

    # ==== Mod Autonom / Manual ====
    if cmd == "mode:autonom":
        current_mode   = "autonom"
        manual_command = None
        return jsonify({"status": "ok", "msg": "Trecut pe autonom"})
    elif cmd == "mode:manual":
        current_mode   = "manual"
        manual_command = None
        return jsonify({"status": "ok", "msg": "Trecut pe manual"})

    # ==== Start / Stop robot ====
    if cmd == "start":
        robot_running  = True
        current_mode   = "autonom"
        manual_command = None
        if obstacle_thread is None or not obstacle_thread.is_alive():
            obstacle_thread = threading.Thread(target=obstacle_avoidance, daemon=True)
            obstacle_thread.start()
        return jsonify({"status": "ok", "msg": "Robot pornit Ă®n mod autonom"})
    elif cmd == "stop":
        stop()
        robot_running  = False
        current_mode   = "manual"
        return jsonify({"status": "ok", "msg": "Robot oprit"})

    # ==== Comenzi manuale ====
    if current_mode == "manual":
        if cmd in ["sus", "inainte"]:
            dist = get_distance(**SENSORS["front"])
            if dist < 15:
                print("Obstacol detectat Ă®n faČ›Ä! ComandÄ ignoratÄ.")
                return jsonify({"status": "blocked", "msg": "Obstacol detectat Ă®n faČ›Ä!"})
            manual_command = "forward"
        elif cmd in ["jos", "spate"]:
            manual_command = "back"
        elif cmd == "stanga":
            manual_command = "left"
        elif cmd == "dreapta":
            manual_command = "right"
        elif cmd == "stop":
            manual_command = "stop"
        return jsonify({"status": "ok", "msg": f"ComandÄ manualÄ: {cmd}"})

    # ==== Implicit ====
    return jsonify({"status": "ok", "msg": "ComandÄ ignoratÄ, robotul e autonom"})

def flask_thread():
    app.run(host="0.0.0.0", port=PORT_FLASK)

if __name__ == "__main__":
    try:
        t = threading.Thread(target=flask_thread, daemon=True)
        t.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        robot_running = False
        GPIO.cleanup()
        print("Oprit robot Č™i curÄČ›at GPIO.")
