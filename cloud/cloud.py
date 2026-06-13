import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
from collections import defaultdict

# ============================================================
# cloud.py  —  CLOUD LAYER  —  Global Orchestrator
#
# 1. Receives summaries from Fog Coordinator
# 2. Receives decisions from Edge agents
# 3. Tracks global city statistics
# 4. Detects city-wide emergency patterns
# 5. Prints a live dashboard in terminal
# 6. Issues global policy commands
# 7. Orchestrates global resource plan (NEW)
#
# Resource Orchestration (NEW):
#   The cloud layer maintains a city-wide resource plan,
#   shifting compute, bandwidth, and sensor capacity toward
#   crisis districts and away from calm ones — globally,
#   across all fog and edge nodes.
# ============================================================

BROKER = "mqtt"
PORT   = 1883

SUB_FOG_SUMMARY = "city/fog/summary"
SUB_DECISIONS   = "city/decisions"
PUB_POLICY      = "city/cloud/policy"

AREAS = ["Industrial Zone", "Residential Zone", "Green Park"]
TOTAL_CITY_BANDWIDTH = 300   # total city-wide bandwidth budget (units)

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
    "level"     : "NORMAL",
    "pm25_limit": 75.0,
    "updated_at": "—",
}

# ── NEW: Global resource plan ─────────────────────────────────
# Cloud orchestrates bandwidth and compute across all nodes globally.
resource_plan = {
    a: {
        "bandwidth"        : 100,    # units out of TOTAL_CITY_BANDWIDTH
        "compute_priority" : "LOW",
        "sensor_interval"  : 1,
        "sensors_active"   : 3,
    }
    for a in AREAS
}


# ── NEW: Global resource orchestration ───────────────────────
def orchestrate_resources(client, hotspot_level, affected_areas, avg_pm25):
    """
    Cloud-level global resource orchestration.

    Shifts compute capacity and bandwidth toward districts in crisis.
    Safe districts are asked to reduce consumption to stay within
    the city-wide budget of TOTAL_CITY_BANDWIDTH units.

    Published as part of the city/cloud/policy message so all
    fog and edge nodes receive the updated global plan.
    """
    safe_areas = [a for a in AREAS if a not in affected_areas]

    if hotspot_level == "CRITICAL" or avg_pm25 > 150:
        for area in affected_areas:
            resource_plan[area] = {
                "bandwidth"       : 90,
                "compute_priority": "HIGH",
                "sensor_interval" : 0.5,
                "sensors_active"  : 5,
            }
        for area in safe_areas:
            resource_plan[area] = {
                "bandwidth"       : 15,
                "compute_priority": "LOW",
                "sensor_interval" : 3,
                "sensors_active"  : 2,
            }

    elif hotspot_level == "HIGH" or avg_pm25 > 75:
        for area in affected_areas:
            resource_plan[area] = {
                "bandwidth"       : 70,
                "compute_priority": "MEDIUM",
                "sensor_interval" : 1,
                "sensors_active"  : 4,
            }
        for area in safe_areas:
            resource_plan[area] = {
                "bandwidth"       : 30,
                "compute_priority": "LOW",
                "sensor_interval" : 2,
                "sensors_active"  : 3,
            }

    else:
        # Normal: equal distribution across all zones
        for area in AREAS:
            resource_plan[area] = {
                "bandwidth"       : 100,
                "compute_priority": "LOW",
                "sensor_interval" : 1,
                "sensors_active"  : 3,
            }

    total_bw = sum(v["bandwidth"] for v in resource_plan.values())
    print(f"\n[CLOUD] 📊 Global Resource Orchestration | Level={hotspot_level} | Total BW={total_bw}")
    for area, plan in resource_plan.items():
        tag = "⚠" if area in affected_areas else "✓"
        print(
            f"[CLOUD]   {tag} {area:20s} | "
            f"BW={plan['bandwidth']:3d} | "
            f"CPU={plan['compute_priority']:6s} | "
            f"Sensors={plan['sensors_active']} | "
            f"Interval={plan['sensor_interval']}s"
        )

    return resource_plan


# ── Print live dashboard ──────────────────────────────────────
def print_dashboard():
    now = datetime.now().strftime("%H:%M:%S")
    print("\n" + "=" * 65)
    print(f"  CLOUD ORCHESTRATOR — LIVE DASHBOARD  [{now}]")
    print("=" * 65)
    print(f"  Global Policy    : {policy['level']}")
    print(f"  PM2.5 Limit      : {policy['pm25_limit']} µg/m³")
    print(f"  Last Avg PM2.5   : {stats['last_avg_pm25']} µg/m³")
    print(f"  Last Avg NOx     : {stats['last_avg_nox']}")
    print(f"  Hotspot Level    : {stats['last_hotspot_level']}")
    print("-" * 65)
    print(f"  Total messages   : {stats['total_messages']}")
    print(f"  Reduce traffic   : {stats['total_reduces']}")
    print(f"  Normal traffic   : {stats['total_normals']}")
    print(f"  Emergencies      : {stats['total_emergencies']}")
    print(f"  Hotspots         : {stats['hotspots_detected']}")
    print("-" * 65)
    print("  Area activity:")
    for area, count in stats["area_counts"].items():
        print(f"    {area}: {count} messages")
    print("-" * 65)
    print("  Severity counts:")
    for sev, count in stats["severity_counts"].items():
        print(f"    {sev:10s}: {count}")
    print("-" * 65)
    print("  Global Resource Plan:")
    for area, plan in resource_plan.items():
        print(
            f"    {area:20s} | BW={plan['bandwidth']:3d} | "
            f"CPU={plan['compute_priority']:6s} | "
            f"Sensors={plan['sensors_active']}"
        )
    print("=" * 65 + "\n")


# ── Update global policy ──────────────────────────────────────
def update_policy(client, hotspot_level, avg_pm25, affected_areas):
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

    # NEW: always orchestrate resources when policy is evaluated
    current_resource_plan = orchestrate_resources(
        client, hotspot_level, affected_areas, avg_pm25
    )

    # If policy changed OR resources need broadcasting — publish
    if policy["level"] != old_level:
        print(f"\n[CLOUD] *** POLICY CHANGE: {old_level} → {policy['level']} ***")

    client.publish(PUB_POLICY, json.dumps({
        "policy"       : policy["level"],
        "pm25_limit"   : policy["pm25_limit"],
        "updated_at"   : policy["updated_at"],
        "reason"       : f"Avg PM2.5={avg_pm25}, Hotspot={hotspot_level}",
        "resource_plan": current_resource_plan,   # NEW
        "layer"        : "cloud"
    }))


# ── Handle fog summary message ────────────────────────────────
def handle_fog_summary(client, payload):
    avg_pm25       = payload.get("avg_pm25",       0)
    avg_nox        = payload.get("avg_nox",        0)
    hotspot        = payload.get("hotspot",        False)
    hotspot_level  = payload.get("hotspot_level",  "LOW")
    affected_areas = payload.get("affected_areas", [])
    fog_command    = payload.get("fog_command",    "NORMAL")

    stats["last_avg_pm25"]      = avg_pm25
    stats["last_avg_nox"]       = avg_nox
    stats["last_hotspot_level"] = hotspot_level

    if hotspot:
        stats["hotspots_detected"] += 1

    if fog_command == "EMERGENCY":
        stats["total_emergencies"] += 1

    print(
        f"[CLOUD] Fog summary received | "
        f"Avg PM2.5={avg_pm25} | "
        f"Hotspot={hotspot_level} | "
        f"Fog cmd={fog_command} | "
        f"Affected={affected_areas}"
    )

    update_policy(client, hotspot_level, avg_pm25, affected_areas)


# ── Handle edge decision message ──────────────────────────────
def handle_edge_decision(payload):
    area       = payload.get("district",            "Unknown")
    decision   = payload.get("decision",            "Unknown")
    severity   = payload.get("severity",            "LOW")
    pm25       = payload.get("pm25",                0)
    resources  = payload.get("resource_assignment", {})

    stats["total_messages"]            += 1
    stats["area_counts"][area]         += 1
    stats["severity_counts"][severity] += 1

    if decision == "Reduce traffic":
        stats["total_reduces"] += 1
    elif decision == "Normal traffic":
        stats["total_normals"] += 1

    print(
        f"[CLOUD] Edge decision | "
        f"{area:20s} | "
        f"PM2.5={pm25:6.1f} | "
        f"Severity={severity:8s} | "
        f"→ {decision} | "
        f"BW={resources.get('bandwidth_limit', '?')}% "
        f"CPU={resources.get('compute_priority', '?')}"
    )

    if stats["total_messages"] % 9 == 0:
        print_dashboard()


# ── MQTT callbacks ────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[CLOUD] Connected to MQTT broker ✅")
        client.subscribe(SUB_FOG_SUMMARY)
        client.subscribe(SUB_DECISIONS)
        print("[CLOUD] Global Orchestrator ready — waiting for data...\n")
    else:
        print(f"[CLOUD] Connection failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        layer   = payload.get("layer", "")

        if msg.topic == SUB_FOG_SUMMARY:
            handle_fog_summary(client, payload)

        elif msg.topic == SUB_DECISIONS and layer == "edge":
            handle_edge_decision(payload)

    except Exception as e:
        print(f"[CLOUD] Error: {e}")


# ── MQTT setup ────────────────────────────────────────────────
print("[CLOUD] Global Orchestrator starting...")
print("-" * 65)
time.sleep(5)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()