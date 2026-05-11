import paho.mqtt.client as mqtt
import json
import time
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
import threading

# ============================================================
# edge_agent.py  —  EDGE LAYER
# Manages ALL 3 areas in one file
# Each area runs as a separate thread
# All areas share the same trained ML model
# ============================================================

BROKER    = "mqtt"
PORT      = 1883
AREAS     = ["Area1", "Area2", "Area3"]

# ── MQTT Topics ─────────────────────────────────────────────
SUB_TOPIC = "city/all"          # sensor data comes in here
PUB_TOPIC = "city/decisions"    # decisions go out here

# ── Load dataset & train ONE shared model ───────────────────
print("[EDGE] Loading dataset...")
data = pd.read_csv("processed_weather.csv")

X = data[["pm25", "visibility", "traffic", "nox"]]
y = data["action"]

model = DecisionTreeClassifier(max_depth=5, random_state=42)
model.fit(X, y)

print(f"[EDGE] ML model trained on {len(data)} rows ✅")
print(f"[EDGE] Managing areas: {AREAS}")
print("-" * 55)

# ── Severity classifier (WHO PM2.5 thresholds) ───────────────
def get_severity(pm25, visibility):
    """
    Returns severity string based on PM2.5 and visibility.
    WHO thresholds:
      LOW      : PM2.5 <= 35
      MEDIUM   : PM2.5 35–75
      HIGH     : PM2.5 75–150
      CRITICAL : PM2.5 > 150 or visibility < 2 km
    """
    if pm25 > 150 or visibility < 2:
        return "CRITICAL"
    elif pm25 > 75 or visibility < 5:
        return "HIGH"
    elif pm25 > 35:
        return "MEDIUM"
    else:
        return "LOW"

# ── Per-area decision function ───────────────────────────────
def make_decision(area, pm25, visibility, traffic, nox):
    """
    Runs ML model for a given area.
    Returns (prediction, severity, decision_text, action_detail)
    """
    input_df = pd.DataFrame(
        [[pm25, visibility, traffic, nox]],
        columns=["pm25", "visibility", "traffic", "nox"]
    )
    prediction = int(model.predict(input_df)[0])
    severity   = get_severity(pm25, visibility)

    # Decision text based on prediction + severity
    if prediction == 1:
        if severity == "CRITICAL":
            decision      = "Close road"
            action_detail = "Immediate closure — dangerous conditions"
        elif severity == "HIGH":
            decision      = "Reduce traffic"
            action_detail = "Allow 30% normal flow only"
        else:
            decision      = "Reduce traffic"
            action_detail = "Reduce speed limit and flow"
    else:
        decision      = "Normal traffic"
        action_detail = "No action needed"

    return prediction, severity, decision, action_detail

# ── Message handler — called for every incoming MQTT message ─
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        area    = payload.get("district")

        # Only handle known areas
        if area not in AREAS:
            return

        pm25       = float(payload.get("pm25",       0))
        visibility = float(payload.get("visibility", 10))
        traffic    = float(payload.get("traffic",    30))
        nox        = float(payload.get("nox",         0))

        prediction, severity, decision, action_detail = make_decision(
            area, pm25, visibility, traffic, nox
        )

        # Print to terminal
        print(
            f"[EDGE | {area}] "
            f"PM2.5={pm25:.1f} | "
            f"Vis={visibility}km | "
            f"Traffic={traffic} | "
            f"NOx={nox:.1f} | "
            f"Severity={severity:8s} | "
            f"→ {decision}"
        )

        # Publish decision to fog coordinator + cloud
        client.publish(PUB_TOPIC, json.dumps({
            "district"     : area,
            "decision"     : decision,
            "severity"     : severity,
            "action_detail": action_detail,
            "pm25"         : pm25,
            "visibility"   : visibility,
            "traffic"      : traffic,
            "nox"          : nox,
            "prediction"   : prediction,
            "layer"        : "edge"
        }))

    except Exception as e:
        print(f"[EDGE] Error processing message: {e}")

# ── Connect callback ─────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[EDGE] Connected to MQTT broker ✅")
        client.subscribe(SUB_TOPIC)
        print(f"[EDGE] Subscribed to: {SUB_TOPIC}")
        print("[EDGE] Waiting for sensor data...\n")
    else:
        print(f"[EDGE] Connection failed — reason code: {reason_code}")

# ── MQTT client setup ────────────────────────────────────────
print(f"[EDGE] Connecting to broker at {BROKER}:{PORT} ...")
time.sleep(3)  # wait for broker to be ready

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)
client.loop_forever()
