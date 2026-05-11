import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

# ============================================================
# fog_coordinator.py  —  FOG LAYER
# Middle layer between Edge agents and Cloud
#
# What it does:
#   1. Receives decisions from all 3 edge areas
#   2. Builds a district pollution map
#   3. Detects hotspots (multiple areas in danger)
#   4. Sends coordinated commands back to edge
#   5. Sends summary report up to cloud
# ============================================================

BROKER        = "mqtt"
PORT          = 1883
AREAS         = ["Area1", "Area2", "Area3"]

# Topics
SUB_DECISIONS = "city/decisions"      # listen to edge agents
PUB_COMMANDS  = "city/fog/commands"   # send commands to edge
PUB_SUMMARY   = "city/fog/summary"    # send summary to cloud

# ── District state — stores latest data from each area ───────
district_state = {
    "Area1": {"pm25": 0, "visibility": 10, "traffic": 0,
               "nox": 0, "severity": "LOW", "decision": "Normal traffic"},
    "Area2": {"pm25": 0, "visibility": 10, "traffic": 0,
               "nox": 0, "severity": "LOW", "decision": "Normal traffic"},
    "Area3": {"pm25": 0, "visibility": 10, "traffic": 0,
               "nox": 0, "severity": "LOW", "decision": "Normal traffic"},
}

# ── Hotspot detection ─────────────────────────────────────────
def detect_hotspot():
    """
    A hotspot is when 2 or more areas are HIGH or CRITICAL.
    Returns (is_hotspot, affected_areas, hotspot_level)
    """
    danger_areas = [
        area for area, state in district_state.items()
        if state["severity"] in ["HIGH", "CRITICAL"]
    ]
    critical_areas = [
        area for area, state in district_state.items()
        if state["severity"] == "CRITICAL"
    ]

    if len(critical_areas) >= 2:
        return True, critical_areas, "CRITICAL"
    elif len(danger_areas) >= 2:
        return True, danger_areas, "HIGH"
    else:
        return False, [], "LOW"

# ── Average pollution across all areas ───────────────────────
def get_district_avg():
    pm25_vals = [s["pm25"] for s in district_state.values()]
    nox_vals  = [s["nox"]  for s in district_state.values()]
    return round(sum(pm25_vals)/len(pm25_vals), 2), \
           round(sum(nox_vals) /len(nox_vals),  2)

# ── Fog layer decision logic ──────────────────────────────────
def fog_decision(hotspot, affected_areas, hotspot_level, avg_pm25):
    """
    Fog coordinator makes a district-wide decision.
    This overrides individual edge decisions when needed.
    """
    if hotspot_level == "CRITICAL":
        return {
            "command"       : "EMERGENCY",
            "action"        : "Close all roads in affected areas",
            "affected_areas": affected_areas,
            "reason"        : f"Critical pollution — avg PM2.5={avg_pm25}"
        }
    elif hotspot_level == "HIGH":
        return {
            "command"       : "RESTRICT",
            "action"        : "Reduce traffic to 30% in affected areas",
            "affected_areas": affected_areas,
            "reason"        : f"High pollution hotspot — avg PM2.5={avg_pm25}"
        }
    else:
        return {
            "command"       : "NORMAL",
            "action"        : "Normal operations",
            "affected_areas": [],
            "reason"        : f"Conditions acceptable — avg PM2.5={avg_pm25}"
        }

# ── Process incoming edge decision ────────────────────────────
def process_edge_decision(client, payload):
    area = payload.get("district")
    if area not in AREAS:
        return

    # Update district state
    district_state[area]["pm25"]       = payload.get("pm25",       0)
    district_state[area]["visibility"] = payload.get("visibility", 10)
    district_state[area]["traffic"]    = payload.get("traffic",    0)
    district_state[area]["nox"]        = payload.get("nox",        0)
    district_state[area]["severity"]   = payload.get("severity",   "LOW")
    district_state[area]["decision"]   = payload.get("decision",   "Normal traffic")

    # Print received edge data
    print(
        f"[FOG] Received from {area:6s} | "
        f"PM2.5={district_state[area]['pm25']:6.1f} | "
        f"Severity={district_state[area]['severity']:8s} | "
        f"Decision={district_state[area]['decision']}"
    )

    # Run hotspot detection
    is_hotspot, affected_areas, hotspot_level = detect_hotspot()
    avg_pm25, avg_nox = get_district_avg()

    # Build fog decision
    fog_cmd = fog_decision(
        is_hotspot, affected_areas, hotspot_level, avg_pm25
    )

    now = datetime.now().strftime("%H:%M:%S")

    # ── If hotspot detected → print warning ──────────────
    if is_hotspot:
        print(f"\n{'='*55}")
        print(f"[FOG] ⚠ HOTSPOT DETECTED at {now}")
        print(f"[FOG] Level    : {hotspot_level}")
        print(f"[FOG] Areas    : {affected_areas}")
        print(f"[FOG] Avg PM2.5: {avg_pm25} µg/m³")
        print(f"[FOG] Command  : {fog_cmd['action']}")
        print(f"{'='*55}\n")
    else:
        print(
            f"[FOG] District OK | "
            f"Avg PM2.5={avg_pm25} | "
            f"Avg NOx={avg_nox} | "
            f"No hotspot\n"
        )

    # ── Publish fog command to edge layer ─────────────────
    client.publish(PUB_COMMANDS, json.dumps({
        "timestamp"     : now,
        "hotspot"       : is_hotspot,
        "hotspot_level" : hotspot_level,
        "fog_command"   : fog_cmd,
        "district_state": district_state,
        "layer"         : "fog"
    }))

    # ── Publish summary to cloud layer ────────────────────
    client.publish(PUB_SUMMARY, json.dumps({
        "timestamp"     : now,
        "avg_pm25"      : avg_pm25,
        "avg_nox"       : avg_nox,
        "hotspot"       : is_hotspot,
        "hotspot_level" : hotspot_level,
        "affected_areas": affected_areas,
        "fog_command"   : fog_cmd["command"],
        "area_severities": {
            a: district_state[a]["severity"] for a in AREAS
        },
        "layer"         : "fog"
    }))

# ── MQTT callbacks ────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[FOG] Connected to MQTT broker ✅")
        client.subscribe(SUB_DECISIONS)
        print(f"[FOG] Subscribed to: {SUB_DECISIONS}")
        print("[FOG] Waiting for edge decisions...\n")
    else:
        print(f"[FOG] Connection failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        # Only process messages from edge layer
        if payload.get("layer") == "fog":
            return
        process_edge_decision(client, payload)
    except Exception as e:
        print(f"[FOG] Error: {e}")

# ── MQTT setup ────────────────────────────────────────────────
print("[FOG] Fog Coordinator starting...")
print(f"[FOG] Managing district: {AREAS}")
print("-" * 55)
time.sleep(4)  # wait for broker + edge agents

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)
client.loop_forever()
