import paho.mqtt.client as mqtt
import json
import time
import random

# ============================================================
# sensor.py — SENSOR LAYER
# Areas: Industrial Zone / Residential Zone / Green Park
# Each area is fully independent with its own profile
# ⏱ Change SEND_INTERVAL to adjust update speed
# ============================================================

BROKER        = "mqtt"
PORT          = 1883
PUB_TOPIC     = "city/all"
SEND_INTERVAL = 1

AREA_PROFILES = {
    "Industrial Zone": {
        "base_pm25"   : 95.0,
        "spike_chance": 0.30,
        "recovery"    : 0.15,
        "base_vis"    : 4.0,
        "base_nox"    : 85.0,
        "base_traffic": 75,
    },
    "Residential Zone": {
        "base_pm25"   : 35.0,
        "spike_chance": 0.15,
        "recovery"    : 0.3,
        "base_vis"    : 8.0,
        "base_nox"    : 20.0,
        "base_traffic": 50,
    },
    "Green Park": {
        "base_pm25"   : 12.0,
        "spike_chance": 0.05,
        "recovery"    : 0.6,
        "base_vis"    : 12.0,
        "base_nox"    : 5.0,
        "base_traffic": 20,
    },
}

area_state = {
    "Industrial Zone":  {"pm25": 95.0,  "nox": 85.0, "visibility": 4.0,  "traffic": 75, "spiking": False},
    "Residential Zone": {"pm25": 35.0,  "nox": 20.0, "visibility": 8.0,  "traffic": 50, "spiking": False},
    "Green Park":       {"pm25": 12.0,  "nox": 5.0,  "visibility": 12.0, "traffic": 20, "spiking": False},
}

def get_time_factor():
    hour = time.localtime().tm_hour
    if 7 <= hour <= 9:    return 1.5
    elif 17 <= hour <= 19: return 1.6
    elif 22 <= hour or hour <= 5: return 0.5
    else: return 1.0

def add_noise(value, pct=0.08):
    return round(value * (1 + pct * random.uniform(-1, 1)), 2)

def update_area(area_name):
    profile = AREA_PROFILES[area_name]
    state   = area_state[area_name]
    time_f  = get_time_factor()

    if not state["spiking"]:
        if random.random() < profile["spike_chance"]:
            state["spiking"]    = True
            spike_mult          = random.uniform(2.0, 4.5)
            state["pm25"]       = profile["base_pm25"] * spike_mult * time_f
            state["nox"]        = profile["base_nox"]  * spike_mult * time_f
            state["visibility"] = max(0.3, profile["base_vis"] - random.uniform(2, 6))
            state["traffic"]    = min(100, int(profile["base_traffic"] * 1.3))
        else:
            state["pm25"]       = add_noise(profile["base_pm25"] * time_f * random.uniform(0.8, 1.2))
            state["nox"]        = add_noise(profile["base_nox"]  * time_f * random.uniform(0.8, 1.2))
            state["visibility"] = add_noise(profile["base_vis"]  * random.uniform(0.9, 1.1))
            state["traffic"]    = int(add_noise(profile["base_traffic"] * time_f))
    else:
        state["pm25"]       = round(state["pm25"]       * (1 - profile["recovery"] * random.uniform(0.1, 0.3)), 2)
        state["nox"]        = round(state["nox"]        * (1 - profile["recovery"] * random.uniform(0.1, 0.3)), 2)
        state["visibility"] = round(min(profile["base_vis"], state["visibility"] + random.uniform(0.1, 0.5)), 2)
        state["traffic"]    = max(profile["base_traffic"], state["traffic"] - random.randint(2, 8))
        if state["pm25"] <= profile["base_pm25"] * 1.2:
            state["spiking"] = False

    state["pm25"]       = max(1.0,  min(400.0, state["pm25"]))
    state["nox"]        = max(0.5,  min(300.0, state["nox"]))
    state["visibility"] = max(0.1,  min(15.0,  state["visibility"]))
    state["traffic"]    = max(5,    min(100,   state["traffic"]))

    return {
        "district"  : area_name,
        "pm25"      : round(state["pm25"], 2),
        "visibility": round(state["visibility"], 2),
        "traffic"   : state["traffic"],
        "nox"       : round(state["nox"], 2),
        "spiking"   : state["spiking"]
    }

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[SENSOR] Connected ✅")
        print(f"[SENSOR] Areas: {list(AREA_PROFILES.keys())}")
        print(f"[SENSOR] Update interval: {SEND_INTERVAL}s\n")

print("[SENSOR] Starting...")
time.sleep(5)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.connect(BROKER, PORT, 60)
client.loop_start()
time.sleep(2)

cycle = 0
while True:
    cycle += 1
    print(f"[SENSOR] ── Cycle {cycle} ──────────────────────────────")
    for area_name in ["Industrial Zone", "Residential Zone", "Green Park"]:
        data    = update_area(area_name)
        spike_t = " 🔴 SPIKE" if data["spiking"] else ""
        client.publish(PUB_TOPIC, json.dumps({
            "district"  : data["district"],
            "pm25"      : data["pm25"],
            "visibility": data["visibility"],
            "traffic"   : data["traffic"],
            "nox"       : data["nox"],
        }))
        print(f"[SENSOR] {data['district']:18s} | PM2.5={data['pm25']:6.1f} | Vis={data['visibility']:4.1f}km | Traffic={data['traffic']:3d} | NOx={data['nox']:5.1f}{spike_t}")
    time.sleep(SEND_INTERVAL)