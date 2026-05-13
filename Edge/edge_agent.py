import paho.mqtt.client as mqtt
import json
import time
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

# ============================================================
# edge_agent.py — EDGE LAYER
# Areas: Industrial Zone / Residential Zone / Green Park
# ============================================================

BROKER    = "mqtt"
PORT      = 1883
AREAS     = ["Industrial Zone", "Residential Zone", "Green Park"]
SUB_TOPIC = "city/all"
PUB_TOPIC = "city/decisions"

print("[EDGE] Loading dataset...")
data  = pd.read_csv("processed_weather.csv")
X     = data[["pm25", "visibility", "traffic", "nox"]]
y     = data["action"]
model = DecisionTreeClassifier(max_depth=5, random_state=42)
model.fit(X, y)
print(f"[EDGE] Model trained on {len(data)} rows ✅")
print(f"[EDGE] Managing: {AREAS}\n")

def get_severity(pm25, visibility):
    if pm25 > 150 or visibility < 2:  return "CRITICAL"
    elif pm25 > 75 or visibility < 5: return "HIGH"
    elif pm25 > 35:                   return "MEDIUM"
    else:                             return "LOW"

def make_decision(pm25, visibility, traffic, nox):
    input_df   = pd.DataFrame([[pm25, visibility, traffic, nox]],
                               columns=["pm25","visibility","traffic","nox"])
    prediction = int(model.predict(input_df)[0])
    severity   = get_severity(pm25, visibility)
    if prediction == 1:
        decision = "Close road" if severity == "CRITICAL" else "Reduce traffic"
    else:
        decision = "Normal traffic"
    return prediction, severity, decision

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[EDGE] Connected ✅")
        client.subscribe(SUB_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload    = json.loads(msg.payload.decode())
        area       = payload.get("district")
        if area not in AREAS:
            return
        pm25       = float(payload.get("pm25",       0))
        visibility = float(payload.get("visibility", 10))
        traffic    = float(payload.get("traffic",    30))
        nox        = float(payload.get("nox",         0))
        prediction, severity, decision = make_decision(pm25, visibility, traffic, nox)
        print(f"[EDGE] {area:18s} | PM2.5={pm25:6.1f} | {severity:8s} | → {decision}")
        client.publish(PUB_TOPIC, json.dumps({
            "district"  : area,
            "decision"  : decision,
            "severity"  : severity,
            "pm25"      : pm25,
            "visibility": visibility,
            "traffic"   : traffic,
            "nox"       : nox,
            "prediction": prediction,
            "layer"     : "edge"
        }))
    except Exception as e:
        print(f"[EDGE] Error: {e}")

time.sleep(3)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()