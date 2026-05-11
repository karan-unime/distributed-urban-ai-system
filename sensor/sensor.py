import paho.mqtt.client as mqtt
import json
import time
import random

# ============================================================
# sensor.py  —  SENSOR LAYER
#
# ⏱ UPDATE INTERVAL: change SEND_INTERVAL below (seconds)
#    SEND_INTERVAL = 1   → updates every 1 second
#    SEND_INTERVAL = 2   → updates every 2 seconds
#    SEND_INTERVAL = 3   → updates every 3 seconds
# ============================================================

BROKER        = "mqtt"
PORT          = 1883
PUB_TOPIC     = "city/all"
SEND_INTERVAL = 5          # ← CHANGE THIS to adjust update speed

# ── Scenario sets — all 3 areas sent together each cycle ─────
# Each ROUND contains data for ALL 3 areas at the same time
# The sensor cycles through rounds: Normal → Moderate → High → Critical → Recovery

ROUNDS = [
    # Round 1 — Normal conditions
    [
        {"district": "Area1", "pm25": 12.0,  "visibility": 10.0, "traffic": 30, "nox": 5.0,   "condition": "Clear"},
        {"district": "Area2", "pm25": 18.0,  "visibility": 9.0,  "traffic": 40, "nox": 8.0,   "condition": "Partly cloudy"},
        {"district": "Area3", "pm25": 22.0,  "visibility": 8.0,  "traffic": 35, "nox": 10.0,  "condition": "Sunny"},
    ],
    # Round 2 — Moderate pollution
    [
        {"district": "Area1", "pm25": 45.0,  "visibility": 6.0,  "traffic": 55, "nox": 25.0,  "condition": "Hazy"},
        {"district": "Area2", "pm25": 60.0,  "visibility": 5.0,  "traffic": 65, "nox": 35.0,  "condition": "Hazy"},
        {"district": "Area3", "pm25": 55.0,  "visibility": 7.0,  "traffic": 60, "nox": 30.0,  "condition": "Overcast"},
    ],
    # Round 3 — High pollution
    [
        {"district": "Area1", "pm25": 90.0,  "visibility": 4.0,  "traffic": 75, "nox": 55.0,  "condition": "Fog"},
        {"district": "Area2", "pm25": 110.0, "visibility": 3.0,  "traffic": 80, "nox": 70.0,  "condition": "Fog"},
        {"district": "Area3", "pm25": 130.0, "visibility": 2.5,  "traffic": 85, "nox": 80.0,  "condition": "Heavy fog"},
    ],
    # Round 4 — Critical
    [
        {"district": "Area1", "pm25": 180.0, "visibility": 1.5,  "traffic": 90, "nox": 110.0, "condition": "Dense fog"},
        {"district": "Area2", "pm25": 200.0, "visibility": 1.0,  "traffic": 95, "nox": 130.0, "condition": "Dense fog"},
        {"district": "Area3", "pm25": 250.0, "visibility": 0.5,  "traffic": 98, "nox": 150.0, "condition": "Smog"},
    ],
    # Round 5 — Recovery
    [
        {"district": "Area1", "pm25": 70.0,  "visibility": 5.5,  "traffic": 60, "nox": 40.0,  "condition": "Improving"},
        {"district": "Area2", "pm25": 50.0,  "visibility": 7.0,  "traffic": 50, "nox": 28.0,  "condition": "Improving"},
        {"district": "Area3", "pm25": 30.0,  "visibility": 8.5,  "traffic": 40, "nox": 15.0,  "condition": "Clearing"},
    ],
]

# ── Add small random noise ────────────────────────────────────
def add_noise(value, pct=0.05):
    noise = value * pct * random.uniform(-1, 1)
    return round(value + noise, 2)

# ── MQTT callbacks ────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[SENSOR] Connected to MQTT broker ✅")
        print(f"[SENSOR] Sending ALL 3 areas every {SEND_INTERVAL}s\n")
    else:
        print(f"[SENSOR] Connection failed: {reason_code}")

# ── MQTT setup ────────────────────────────────────────────────
print("[SENSOR] Starting up...")
time.sleep(5)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.connect(BROKER, PORT, 60)
client.loop_start()
time.sleep(2)

# ── Main loop ─────────────────────────────────────────────────
print(f"[SENSOR] Live — update interval: {SEND_INTERVAL} second(s)\n")

cycle = 0
while True:
    # Pick current round (cycles through all 5 rounds)
    round_data = ROUNDS[cycle % len(ROUNDS)]

    print(f"[SENSOR] ── Round {(cycle % len(ROUNDS)) + 1} ──────────────────────────")

    # Send ALL 3 areas at the same time
    for scenario in round_data:
        payload = {
            "district"  : scenario["district"],
            "pm25"      : add_noise(scenario["pm25"]),
            "visibility": add_noise(scenario["visibility"]),
            "traffic"   : int(add_noise(scenario["traffic"])),
            "nox"       : add_noise(scenario["nox"]),
            "condition" : scenario["condition"]
        }
        client.publish(PUB_TOPIC, json.dumps(payload))
        print(
            f"[SENSOR] {payload['district']:6s} | "
            f"PM2.5={payload['pm25']:6.1f} | "
            f"Vis={payload['visibility']:4.1f}km | "
            f"Traffic={payload['traffic']:3d} | "
            f"NOx={payload['nox']:6.1f}"
        )

    cycle += 1
    time.sleep(SEND_INTERVAL)   # ← controlled by SEND_INTERVAL above