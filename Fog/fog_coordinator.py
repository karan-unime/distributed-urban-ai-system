import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

# ============================================================
# fog_coordinator.py — FOG LAYER
# Areas: Industrial Zone / Residential Zone / Green Park
# ============================================================

BROKER        = "mqtt"
PORT          = 1883
AREAS         = ["Industrial Zone", "Residential Zone", "Green Park"]
SUB_DECISIONS = "city/decisions"
PUB_COMMANDS  = "city/fog/commands"
PUB_SUMMARY   = "city/fog/summary"

district_state = {a: {"pm25":0,"visibility":10,"traffic":0,"nox":0,"severity":"LOW","decision":"Normal traffic"} for a in AREAS}

def detect_hotspot():
    danger   = [a for a,s in district_state.items() if s["severity"] in ["HIGH","CRITICAL"]]
    critical = [a for a,s in district_state.items() if s["severity"] == "CRITICAL"]
    if len(critical) >= 2: return True, critical, "CRITICAL"
    elif len(danger) >= 2: return True, danger,   "HIGH"
    else:                  return False, [],       "LOW"

def get_avg():
    return (round(sum(s["pm25"] for s in district_state.values())/len(AREAS),2),
            round(sum(s["nox"]  for s in district_state.values())/len(AREAS),2))

def fog_decision(hotspot, affected, level, avg_pm25):
    if level == "CRITICAL":
        return {"command":"EMERGENCY","action":"Close all roads in affected zones","affected_areas":affected,"reason":f"Critical pollution avg PM2.5={avg_pm25}"}
    elif level == "HIGH":
        return {"command":"RESTRICT","action":"Reduce traffic to 30% in affected zones","affected_areas":affected,"reason":f"High pollution hotspot avg PM2.5={avg_pm25}"}
    else:
        return {"command":"NORMAL","action":"Normal operations","affected_areas":[],"reason":f"Conditions acceptable avg PM2.5={avg_pm25}"}

def process_edge_decision(client, payload):
    area = payload.get("district")
    if area not in AREAS: return
    district_state[area].update({
        "pm25"      : payload.get("pm25",       0),
        "visibility": payload.get("visibility", 10),
        "traffic"   : payload.get("traffic",    0),
        "nox"       : payload.get("nox",        0),
        "severity"  : payload.get("severity",   "LOW"),
        "decision"  : payload.get("decision",   "Normal traffic"),
    })
    print(f"[FOG] {area:18s} | PM2.5={district_state[area]['pm25']:6.1f} | {district_state[area]['severity']:8s} | {district_state[area]['decision']}")
    is_hotspot, affected, level = detect_hotspot()
    avg_pm25, avg_nox = get_avg()
    fog_cmd = fog_decision(is_hotspot, affected, level, avg_pm25)
    now = datetime.now().strftime("%H:%M:%S")
    if is_hotspot:
        print(f"\n{'='*55}\n[FOG] ⚠ HOTSPOT {level} at {now}\n[FOG] Zones: {affected}\n[FOG] Avg PM2.5: {avg_pm25}\n[FOG] → {fog_cmd['action']}\n{'='*55}\n")
    else:
        print(f"[FOG] District OK | Avg PM2.5={avg_pm25} | Avg NOx={avg_nox}\n")
    client.publish(PUB_COMMANDS, json.dumps({"timestamp":now,"hotspot":is_hotspot,"hotspot_level":level,"fog_command":fog_cmd,"layer":"fog"}))
    client.publish(PUB_SUMMARY,  json.dumps({"timestamp":now,"avg_pm25":avg_pm25,"avg_nox":avg_nox,"hotspot":is_hotspot,"hotspot_level":level,"affected_areas":affected,"fog_command":fog_cmd["command"],"area_severities":{a:district_state[a]["severity"] for a in AREAS},"layer":"fog"}))

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[FOG] Connected ✅")
        client.subscribe(SUB_DECISIONS)
        print(f"[FOG] Monitoring: {AREAS}\n")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if payload.get("layer") != "fog":
            process_edge_decision(client, payload)
    except Exception as e:
        print(f"[FOG] Error: {e}")

print("[FOG] Fog Coordinator starting...")
time.sleep(4)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()