from flask import Flask, render_template, jsonify
import serial
import threading
import time

app = Flask(__name__)

ARDUINO_PORT = "COM11"
BAUD_RATE = 9600
RECONNECT_DELAY = 3  # seconds between reconnect attempts if the Arduino drops

# Latest real Arduino data
data = {
    "vehicle": "D01",
    "distance": None,
    "closing_speed": 0.0,
    "ttc": None,
    "risk": "WAITING",
    "action": "WAITING",
    "led": "OFF",
    "buzzer": "OFF",
    "sensor": "OFFLINE",
    "last_update": 0
}

alerts = []

lock = threading.Lock()


def read_arduino():
    """Runs forever in a background thread. Reconnects automatically if the
    serial connection drops, so the dashboard doesn't need a server restart."""

    global data

    while True:

        try:
            ser = serial.Serial(
                ARDUINO_PORT,
                BAUD_RATE,
                timeout=1
            )

            time.sleep(2)

            print("Arduino connected on", ARDUINO_PORT)

            with lock:
                data["sensor"] = "ONLINE"

            while True:

                line = ser.readline().decode(
                    "utf-8",
                    errors="ignore"
                ).strip()

                if not line:
                    continue

                print(line)

                # -------------------------
                # DISTANCE
                # -------------------------

                if line.startswith("DISTANCE:"):

                    value = line.split(":", 1)[1]

                    try:
                        distance = float(value)

                        with lock:
                            data["distance"] = distance
                            data["last_update"] = time.time()

                    except ValueError:
                        pass


                # -------------------------
                # CLOSING SPEED
                # -------------------------

                elif line.startswith("CLOSING_SPEED:"):

                    value = line.split(":", 1)[1]

                    try:
                        speed = float(value)

                        with lock:
                            data["closing_speed"] = speed

                    except ValueError:
                        pass


                # -------------------------
                # TTC
                # -------------------------

                elif line.startswith("TTC:"):

                    value = line.split(":", 1)[1]

                    if value == "NA":

                        with lock:
                            data["ttc"] = None

                    else:

                        try:
                            ttc = float(value)

                            with lock:
                                data["ttc"] = ttc

                        except ValueError:
                            pass


                # -------------------------
                # RISK
                # -------------------------

                elif line.startswith("RISK:"):

                    risk = line.split(":", 1)[1]

                    with lock:

                        old_risk = data["risk"]

                        data["risk"] = risk

                        if (
                            risk != old_risk
                            and risk in ["WARNING", "CRITICAL"]
                        ):

                            alerts.insert(
                                0,
                                {
                                    "time": time.strftime("%H:%M:%S"),
                                    "risk": risk,
                                    "distance": data["distance"],
                                    "ttc": data["ttc"]
                                }
                            )

                            if len(alerts) > 20:
                                alerts.pop()


                # -------------------------
                # ACTION
                # -------------------------

                elif line.startswith("ACTION:"):

                    action = line.split(":", 1)[1]

                    with lock:
                        data["action"] = action


                # -------------------------
                # LED
                # -------------------------

                elif line.startswith("LED:"):

                    led = line.split(":", 1)[1]

                    with lock:
                        data["led"] = led


                # -------------------------
                # BUZZER
                # -------------------------

                elif line.startswith("BUZZER:"):

                    buzzer = line.split(":", 1)[1]

                    with lock:
                        data["buzzer"] = buzzer


                # -------------------------
                # SENSOR ERROR
                # -------------------------

                elif line == "STATUS:SENSOR_ERROR":

                    with lock:
                        data["sensor"] = "ERROR"

        except Exception as e:

            print("Arduino connection error:", e)

            with lock:
                data["sensor"] = "OFFLINE"

            time.sleep(RECONNECT_DELAY)


# =====================================
# DASHBOARD
# =====================================

@app.route("/")
def home():

    return render_template("index.html")


# =====================================
# REAL-TIME STATUS API
# =====================================

@app.route("/api/status")
def status():

    with lock:

        result = data.copy()

        # Sensor timeout
        if (
            time.time() - result["last_update"] > 3
            and result["distance"] is not None
        ):

            result["sensor"] = "STALE"

        return jsonify(result)


# =====================================
# ALERT API
# =====================================

@app.route("/api/alerts")
def get_alerts():

    with lock:

        return jsonify(alerts)


@app.route("/api/alerts/clear")
def clear_alerts():

    with lock:

        alerts.clear()

    return jsonify({
        "success": True
    })


# =====================================
# HEALTH
# =====================================

@app.route("/api/health")
def health():

    with lock:

        return jsonify({
            "arduino": data["sensor"],
            "distance": data["distance"],
            "risk": data["risk"]
        })


# =====================================
# START
# =====================================

if __name__ == "__main__":

    thread = threading.Thread(
        target=read_arduino,
        daemon=True
    )

    thread.start()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
