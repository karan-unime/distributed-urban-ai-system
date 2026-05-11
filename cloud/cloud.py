import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
from collections import defaultdict

# ============================================================
# cloud.py  —  CLOUD LAYER  —  Global Orchestrator
#
# What it does:
#   1. Receives summaries from Fog Coordinator
#   2. Receives decisions from Edge agents
#   3. Tracks global city statistics
#   4. Detects city-wide emergency patterns
#   5. Prints a live dashboard in terminal
#   6. Issues global policy commands
# ============================================================

BROKER = "mqtt"
PORT   = 1883

# Topics to subscribe
SUB_FOG_SUMMARY = "city/fog/summary"   # from fog coordinator
SUB_DECISIONS   = "city/decisions"     # from edge agents
PUB_POLICY      = "city/cloud/policy"  # global policy broadcast

# ── Global city statistics ────────────────────────────────────
stats = {
    "total_messages"    : 0,
    "total_reduces"     : 0,
    "total_normals"     : 0,
    "total_emergencies" : 0,
    "hotspots_detected" : 0,
    "last_avg_pm25"     : 0.0,
    "last_avg_nox"      : 0.0,
    "last_hotspot_level": "NONE",
    "area_counts"       : defaultdict(int),
    "severity_counts"   : defaultdict(int),
}

# ── Global policy state ───────────────────────────────────────
policy = {
    "level"     : "NORMAL",   # NORMAL / ALERT / EMERGENCY
    "pm25_limit": 75.0,       # threshold for action
    "updated_at": "—",
}

# ── Print live dashboard ──────────────────────────────────────
def print_dashboard():
    now = datetime.now().strftime("%H:%M:%S")
    print("\n" + "=" * 60)
    print(f"  CLOUD ORCHESTRATOR — LIVE DASHBOARD  [{now}]")
    print("=" * 60)
    print(f"  Global Policy    : {policy['level']}")
    print(f"  PM2.5 Limit      : {policy['pm25_limit']} µg/m³")
    print(f"  Last Avg PM2.5   : {stats['last_avg_pm25']} µg/m³")
    print(f"  Last Avg NOx     : {stats['last_avg_nox']}")
    print(f"  Hotspot Level    : {stats['last_hotspot_level']}")
    print("-" * 60)
    print(f"  Total messages   : {stats['total_messages']}")
    print(f"  Reduce traffic   : {stats['total_reduces']}")
    print(f"  Normal traffic   : {stats['total_normals']}")
    print(f"  Emergencies      : {stats['total_emergencies']}")
    print(f"  Hotspots         : {stats['hotspots_detected']}")
    print("-" * 60)
    print("  Area activity:")
    for area, count in stats["area_counts"].items():
        print(f"    {area}: {count} messages")
    print("-" * 60)
    print("  Severity counts:")
    for sev, count in stats["severity_counts"].items():
        print(f"    {sev:10s}: {count}")
    print("=" * 60 + "\n")

# ── Update global policy based on fog summary ─────────────────
def update_policy(client, hotspot_level, avg_pm25):
    old_level = policy["level"]

    if hotspot_level == "CRITICAL" or avg_pm25 > 150:
        policy["level"]      = "EMERGENCY"
        policy["pm25_limit"] = 50.0
    elif hotspot_level == "HIGH" or avg_pm25 > 75:
        policy["level"]      = "ALERT"
        policy["pm25_limit"] = 65.0
    else:
        policy["level"]      = "NORMAL"
        policy["pm25_limit"] = 75.0

    policy["updated_at"] = datetime.now().strftime("%H:%M:%S")

    # If policy changed — broadcast to all layers
    if policy["level"] != old_level:
        print(f"\n[CLOUD] *** POLICY CHANGE: {old_level} → {policy['level']} ***")
        client.publish(PUB_POLICY, json.dumps({
            "policy"    : policy["level"],
            "pm25_limit": policy["pm25_limit"],
            "updated_at": policy["updated_at"],
            "reason"    : f"Avg PM2.5={avg_pm25}, Hotspot={hotspot_level}",
            "layer"     : "cloud"
        }))

# ── Handle fog summary message ────────────────────────────────
def handle_fog_summary(client, payload):
    avg_pm25       = payload.get("avg_pm25",       0)
    avg_nox        = payload.get("avg_nox",        0)
    hotspot        = payload.get("hotspot",        False)
    hotspot_level  = payload.get("hotspot_level",  "LOW")
    affected_areas = payload.get("affected_areas", [])
    fog_command    = payload.get("fog_command",    "NORMAL")
    timestamp      = payload.get("timestamp",      "—")

    # Update stats
    stats["last_avg_pm25"]    = avg_pm25
    stats["last_avg_nox"]     = avg_nox
    stats["last_hotspot_level"] = hotspot_level

    if hotspot:
        stats["hotspots_detected"] += 1

    if fog_command == "EMERGENCY":
        stats["total_emergencies"] += 1

    print(
        f"[CLOUD] Fog summary received | "
        f"Avg PM2.5={avg_pm25} | "
        f"Hotspot={hotspot_level} | "
        f"Fog cmd={fog_command}"
    )

    # Update and possibly broadcast new policy
    update_policy(client, hotspot_level, avg_pm25)

# ── Handle edge decision message ──────────────────────────────
def handle_edge_decision(payload):
    area     = payload.get("district",  "Unknown")
    decision = payload.get("decision",  "Unknown")
    severity = payload.get("severity",  "LOW")
    pm25     = payload.get("pm25",      0)

    stats["total_messages"]        += 1
    stats["area_counts"][area]     += 1
    stats["severity_counts"][severity] += 1

    if decision == "Reduce traffic":
        stats["total_reduces"] += 1
    elif decision == "Normal traffic":
        stats["total_normals"] += 1

    print(
        f"[CLOUD] Edge decision | "
        f"{area:6s} | "
        f"PM2.5={pm25:6.1f} | "
        f"Severity={severity:8s} | "
        f"→ {decision}"
    )

    # Print dashboard every 9 messages (3 areas × 3 cycles)
    if stats["total_messages"] % 9 == 0:
        print_dashboard()

# ── MQTT callbacks ────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[CLOUD] Connected to MQTT broker ✅")
        client.subscribe(SUB_FOG_SUMMARY)
        client.subscribe(SUB_DECISIONS)
        print(f"[CLOUD] Subscribed to fog summaries and edge decisions")
        print("[CLOUD] Global Orchestrator ready — waiting for data...\n")
    else:
        print(f"[CLOUD] Connection failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        layer   = payload.get("layer", "")

        # Route message to correct handler
        if msg.topic == SUB_FOG_SUMMARY:
            handle_fog_summary(client, payload)

        elif msg.topic == SUB_DECISIONS and layer == "edge":
            handle_edge_decision(payload)

    except Exception as e:
        print(f"[CLOUD] Error: {e}")

# ── MQTT setup ────────────────────────────────────────────────
print("[CLOUD] Global Orchestrator starting...")
print("-" * 60)
time.sleep(5)  # wait for all other layers to be ready

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)
client.loop_forever()
