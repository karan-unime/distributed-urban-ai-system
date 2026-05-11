import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import json
from datetime import datetime
from collections import deque

app = Flask(__name__)
app.config["SECRET_KEY"] = "urban_system_2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

BROKER = "mqtt"
PORT   = 1883

state = {
    "cloud_policy"      : "NORMAL",
    "cloud_pm25_limit"  : 75.0,
    "cloud_updated"     : "—",
    "cloud_total_msg"   : 0,
    "cloud_reduces"     : 0,
    "cloud_normals"     : 0,
    "cloud_emergencies" : 0,
    "cloud_hotspots"    : 0,
    "fog_hotspot"       : False,
    "fog_hotspot_level" : "NONE",
    "fog_avg_pm25"      : 0.0,
    "fog_avg_nox"       : 0.0,
    "fog_command"       : "NORMAL",
    "fog_affected_areas": [],
    "fog_updated"       : "—",
    "areas": {
        "Area1": {"pm25": 0, "visibility": 10, "traffic": 0, "nox": 0, "severity": "LOW", "decision": "—"},
        "Area2": {"pm25": 0, "visibility": 10, "traffic": 0, "nox": 0, "severity": "LOW", "decision": "—"},
        "Area3": {"pm25": 0, "visibility": 10, "traffic": 0, "nox": 0, "severity": "LOW", "decision": "—"},
    }
}

event_log = deque(maxlen=50)

def add_log(layer, message, level="normal"):
    event_log.appendleft({"time": datetime.now().strftime("%H:%M:%S"), "layer": layer, "msg": message, "level": level})

def push_update():
    socketio.emit("update", {"state": state, "event_log": list(event_log)})

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        topic   = msg.topic

        if topic == "city/decisions":
            area     = payload.get("district")
            decision = payload.get("decision", "—")
            severity = payload.get("severity", "LOW")
            pm25     = payload.get("pm25",      0)
            vis      = payload.get("visibility",10)
            traffic  = payload.get("traffic",   0)
            nox      = payload.get("nox",       0)
            if area in state["areas"]:
                state["areas"][area] = {"pm25": pm25, "visibility": vis, "traffic": traffic, "nox": nox, "severity": severity, "decision": decision}
                state["cloud_total_msg"] += 1
                if decision == "Reduce traffic":   state["cloud_reduces"]     += 1
                elif decision == "Normal traffic": state["cloud_normals"]     += 1
                elif decision == "Close road":     state["cloud_emergencies"] += 1
                level = "critical" if severity=="CRITICAL" else "high" if severity=="HIGH" else "medium" if severity=="MEDIUM" else "normal"
                add_log("EDGE", f"{area} | PM2.5={pm25} | {severity} → {decision}", level)

        elif topic == "city/fog/summary":
            state["fog_hotspot"]        = payload.get("hotspot",       False)
            state["fog_hotspot_level"]  = payload.get("hotspot_level", "NONE")
            state["fog_avg_pm25"]       = payload.get("avg_pm25",      0)
            state["fog_avg_nox"]        = payload.get("avg_nox",       0)
            state["fog_command"]        = payload.get("fog_command",   "NORMAL")
            state["fog_affected_areas"] = payload.get("affected_areas",[])
            state["fog_updated"]        = datetime.now().strftime("%H:%M:%S")
            if state["fog_hotspot"]:
                state["cloud_hotspots"] += 1
                level = "critical" if state["fog_hotspot_level"]=="CRITICAL" else "high"
                add_log("FOG", f"⚠ HOTSPOT {state['fog_hotspot_level']} | Areas:{state['fog_affected_areas']} | PM2.5={state['fog_avg_pm25']} | CMD:{state['fog_command']}", level)
            else:
                add_log("FOG", f"District OK | Avg PM2.5={state['fog_avg_pm25']} | Avg NOx={state['fog_avg_nox']}", "normal")

        elif topic == "city/cloud/policy":
            old = state["cloud_policy"]
            state["cloud_policy"]     = payload.get("policy",     "NORMAL")
            state["cloud_pm25_limit"] = payload.get("pm25_limit", 75.0)
            state["cloud_updated"]    = payload.get("updated_at", "—")
            add_log("CLOUD", f"Policy: {old} → {state['cloud_policy']} | Limit={state['cloud_pm25_limit']}",
                "critical" if state["cloud_policy"]=="EMERGENCY" else "high" if state["cloud_policy"]=="ALERT" else "normal")

        push_update()

    except Exception as e:
        print(f"[DASHBOARD] Error: {e}")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[DASHBOARD] Connected to MQTT ✅")
        client.subscribe("city/decisions")
        client.subscribe("city/fog/summary")
        client.subscribe("city/cloud/policy")
    else:
        print(f"[DASHBOARD] MQTT failed: {reason_code}")

def start_mqtt():
    import time
    time.sleep(4)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_forever()

eventlet.spawn(start_mqtt)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/state")
def api_state():
    return {"state": state, "event_log": list(event_log)}

if __name__ == "__main__":
    print("[DASHBOARD] Starting at http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)