import paho.mqtt.client as mqtt
import json
import time
import pandas as pd

# ============================================================
# sensor.py  —  SENSOR LAYER
#
# REAL DATA VERSION — reads directly from GlobalWeatherRepository
# No random values. Every reading comes from a real city.
#
# Zone → Real City Mapping (1 zone = 1 city = 1 country):
#
#   Industrial Zone  → Jakarta, Indonesia   (high pollution)
#   Residential Zone → Tehran, Iran         (medium pollution)
#   Green Park       → Canberra, Australia  (low pollution)
#
# Each zone streams real rows from its assigned city,
# one row per second, cycling through all available rows.
# ============================================================

BROKER        = "mqtt"
PORT          = 1883
PUB_TOPIC     = "city/all"
SEND_INTERVAL = 1   # seconds between updates

# ── Load real dataset ────────────────────────────────────────
print("[SENSOR] Loading GlobalWeatherRepository.csv ...")
df = pd.read_csv("GlobalWeatherRepository.csv")

# Clean: remove physically impossible values
df = df[df["wind_kph"] < 200]
df = df.dropna(subset=[
    "air_quality_PM2.5",
    "visibility_km",
    "air_quality_Nitrogen_dioxide",
    "humidity",
    "wind_kph",
    "condition_text"
])

print(f"[SENSOR] Dataset loaded: {len(df)} rows from {df['country'].nunique()} countries")

# ── Zone → Real city mapping ─────────────────────────────────
# Each zone is mapped to ONE real city from a DIFFERENT country,
# chosen to match the zone's intended pollution profile.
#
#   Industrial Zone  → Jakarta, Indonesia   (avg PM2.5 ≈ 145 — high)
#   Residential Zone → Tehran, Iran         (avg PM2.5 ≈ 55  — medium)
#   Green Park       → Canberra, Australia  (avg PM2.5 ≈ 8   — low)

ZONE_CITIES = {
    "Industrial Zone" : ["Jakarta"],
    "Residential Zone": ["Tehran"],
    "Green Park"      : ["Canberra"],
}

# ── Extract real rows per zone ───────────────────────────────
zone_data = {}
for zone, cities in ZONE_CITIES.items():
    rows = df[df["location_name"].isin(cities)].copy()
    rows = rows.reset_index(drop=True)
    zone_data[zone] = rows
    print(
        f"[SENSOR] {zone:20s} → "
        f"{len(rows)} real rows from: {cities[:3]}"
    )

print()

# Check if we have enough rows
for zone, rows in zone_data.items():
    if len(rows) == 0:
        print(f"[SENSOR] WARNING: No rows found for {zone}!")
        print(f"[SENSOR] Using fallback: all rows with matching PM2.5 range")
        if zone == "Industrial Zone":
            zone_data[zone] = df[df["air_quality_PM2.5"] > 75].copy().reset_index(drop=True)
        elif zone == "Residential Zone":
            zone_data[zone] = df[
                (df["air_quality_PM2.5"] >= 20) &
                (df["air_quality_PM2.5"] <= 75)
            ].copy().reset_index(drop=True)
        else:
            zone_data[zone] = df[df["air_quality_PM2.5"] < 20].copy().reset_index(drop=True)
        print(f"[SENSOR] Fallback rows: {len(zone_data[zone])}")

# ── Current index per zone (cycles through rows) ─────────────
zone_index = {zone: 0 for zone in ZONE_CITIES}

# ── Get next real row for a zone ─────────────────────────────
def get_next_reading(zone):
    """
    Returns the next real row from the dataset for this zone.
    Cycles back to the beginning when all rows are used.
    """
    rows = zone_data[zone]
    idx  = zone_index[zone] % len(rows)
    row  = rows.iloc[idx]
    zone_index[zone] += 1

    # Compute traffic score from real humidity and wind
    traffic = int(row["humidity"] * 0.4 + row["wind_kph"] * 0.6)
    traffic = max(5, min(100, traffic))

    return {
        "district"   : zone,
        "pm25"       : round(float(row["air_quality_PM2.5"]), 2),
        "visibility" : round(float(row["visibility_km"]), 2),
        "nox"        : round(float(row["air_quality_Nitrogen_dioxide"]), 2),
        "traffic"    : traffic,
        "condition"  : str(row["condition_text"]),
        "city"       : str(row["location_name"]),
        "country"    : str(row["country"]),
        "humidity"   : float(row["humidity"]),
        "wind_kph"   : float(row["wind_kph"]),
    }

# ── MQTT ─────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[SENSOR] Connected to MQTT broker ✅")
        print("[SENSOR] Streaming REAL data from GlobalWeatherRepository")
        print(f"[SENSOR] Update interval: {SEND_INTERVAL}s\n")
        for zone, cities in ZONE_CITIES.items():
            print(f"  {zone:20s} ← real rows from {cities}")
        print()

print("[SENSOR] Starting ...")
time.sleep(5)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.connect(BROKER, PORT, 60)
client.loop_start()
time.sleep(2)

# ── Main loop ─────────────────────────────────────────────────
print("[SENSOR] Streaming real data ...\n")
cycle = 0

while True:
    cycle += 1
    print(f"[SENSOR] ── Cycle {cycle} (Real data) ──────────────────────")

    for zone in ["Industrial Zone", "Residential Zone", "Green Park"]:
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
            f"({reading['condition']})"
        )
    time.sleep(SEND_INTERVAL)
    
