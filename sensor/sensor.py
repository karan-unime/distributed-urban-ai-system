import paho.mqtt.client as mqtt
import json
import time
import pandas as pd

# ============================================================
# sensor.py  —  SENSOR LAYER
#
# BEIJING MULTI-SITE AIR QUALITY VERSION
#
# Source: UCI Beijing Multi-Site Air-Quality Data Set
# (Beijing Municipal Environmental Monitoring Center,
#  hourly readings, March 2013 - February 2017)
#
# One city (Beijing), three monitoring-station districts:
#
#   Industrial District  -> Gucheng, Beijing   (high pollution)
#   Residential District -> Dongsi, Beijing    (medium-high pollution)
#   Green District       -> Dingling, Beijing  (suburban/forest, lowest)
#
# Each district streams its real historical hourly readings,
# in chronological order, cycling back to the start when the
# 4-year record is exhausted.
#
# Requires beijing_<District>.csv files produced by
# process_dataset.py (run it first if these are missing).
# ============================================================

BROKER        = "mqtt"
PORT          = 1883
PUB_TOPIC     = "city/all"
SEND_INTERVAL = 0.5   # seconds between updates (faster for demos)

AREAS = ["Industrial District", "Residential District", "Green District"]

ZONE_FILES = {
    "Industrial District" : "beijing_Industrial_District.csv",
    "Residential District": "beijing_Residential_District.csv",
    "Green District"      : "beijing_Green_District.csv",
}

# ── DEMO MODE: start near the Dec 2013 winter smog episode ────
# Beijing's worst pollution occurs Nov-Feb (heating season).
# Starting at row 0 (March 2013) means waiting through ~6,000
# hours of mild spring/summer data before any hotspot triggers.
#
# These offsets start ~100 hours BEFORE each district's first
# major smog spike (PM2.5 > 150) in Dec 2013, so the dashboard
# shows STABLE -> RISING -> RISING_FAST -> HIGH/CRITICAL ->
# resource reallocation within the first couple of minutes.
#
# Set DEMO_MODE = False to stream from the start of the
# 4-year record (2013-03-01) instead.
DEMO_MODE = True

START_INDEX = {
    "Industrial District" : 6300,   # ~2013-11-27, spike at idx 6411 (2013-12-01)
    "Residential District": 6300,   # ~2013-11-27, spike at idx 6438 (2013-12-01)
    "Green District"      : 6000,   # ~2013-11-29, spike at idx 6131 (2013-12-02)
}

# ── Load real Beijing data per district ───────────────────────
print("[SENSOR] Loading Beijing district datasets ...")
zone_data = {}
for zone, fname in ZONE_FILES.items():
    rows = pd.read_csv(fname)
    rows = rows.reset_index(drop=True)
    zone_data[zone] = rows
    city    = rows["city"].iloc[0]
    country = rows["country"].iloc[0]
    print(
        f"[SENSOR] {zone:20s} -> {len(rows):6d} hourly rows | "
        f"{city}, {country} | "
        f"PM2.5 mean={rows['pm25'].mean():.1f}"
    )
print()

# ── Current index per zone (cycles through rows chronologically) ─
if DEMO_MODE:
    zone_index = {zone: START_INDEX[zone] for zone in AREAS}
    print("[SENSOR] DEMO MODE ON — starting near Dec 2013 winter smog episode")
    for zone in AREAS:
        row = zone_data[zone].iloc[zone_index[zone]]
        print(
            f"  {zone:20s} starting at "
            f"{int(row['year'])}-{int(row['month']):02d}-{int(row['day']):02d} "
            f"{int(row['hour']):02d}:00  (PM2.5={row['pm25']:.1f})"
        )
    print()
else:
    zone_index = {zone: 0 for zone in AREAS}


def get_next_reading(zone):
    """
    Returns the next real hourly row from the dataset for this zone,
    in chronological order. Cycles back to 2013-03-01 when the
    4-year record (Feb 2017) is exhausted.
    """
    rows = zone_data[zone]
    idx  = zone_index[zone] % len(rows)
    row  = rows.iloc[idx]
    zone_index[zone] += 1

    return {
        "district"  : zone,
        "pm25"      : float(row["pm25"]),
        "visibility": float(row["visibility"]),
        "nox"       : float(row["nox"]),
        "traffic"   : int(row["traffic"]),
        "condition" : str(row["condition"]),
        "city"      : str(row["city"]),
        "country"   : "",  # city col already contains "Gucheng, Beijing"
        "timestamp" : f"{int(row['year'])}-{int(row['month']):02d}-{int(row['day']):02d} {int(row['hour']):02d}:00",
    }


# ── MQTT ─────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[SENSOR] Connected to MQTT broker ✅")
        print("[SENSOR] Streaming REAL Beijing air-quality data (hourly, chronological)")
        print(f"[SENSOR] Update interval: {SEND_INTERVAL}s\n")
        for zone, fname in ZONE_FILES.items():
            city = zone_data[zone]["city"].iloc[0]
            print(f"  {zone:20s} <- {fname}  ({city})")
        print()


print("[SENSOR] Starting ...")
time.sleep(5)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.connect(BROKER, PORT, 60)
client.loop_start()
time.sleep(2)

# ── Main loop ─────────────────────────────────────────────────
print("[SENSOR] Streaming real Beijing data ...\n")
cycle = 0

while True:
    cycle += 1
    print(f"[SENSOR] -- Cycle {cycle} (Beijing real data) --------------------------")

    for zone in AREAS:
        reading = get_next_reading(zone)

        # Publish to MQTT
        client.publish(PUB_TOPIC, json.dumps({
            "district"  : reading["district"],
            "pm25"      : reading["pm25"],
            "visibility": reading["visibility"],
            "nox"       : reading["nox"],
            "traffic"   : reading["traffic"],
            "city"      : reading["city"],
            "country"   : reading["country"],
            "condition" : reading["condition"],
        }))

        print(
            f"[SENSOR] {reading['district']:20s} | "
            f"PM2.5={reading['pm25']:6.1f} | "
            f"Vis={reading['visibility']:5.1f}km | "
            f"NOx={reading['nox']:6.1f} | "
            f"Traffic={reading['traffic']:3d} | "
            f"{reading['city']}, {reading['country']} "
            f"({reading['condition']}) @ {reading['timestamp']}"
        )

    time.sleep(SEND_INTERVAL)