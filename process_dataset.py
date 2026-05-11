import pandas as pd

# ============================================================
# process_dataset.py
# Reads GlobalWeatherRepository.csv
# Produces processed_weather.csv used by ALL agents
# ============================================================

print("Loading GlobalWeatherRepository.csv ...")

df = pd.read_csv("GlobalWeatherRepository.csv")

# ── Step 1: Keep only the columns we need ──────────────────
df = df[[
    "visibility_km",
    "humidity",
    "wind_kph",
    "condition_text",
    "air_quality_PM2.5",
    "air_quality_Nitrogen_dioxide"
]]

# ── Step 2: Drop rows with missing values ──────────────────
df = df.dropna()

# ── Step 3: Rename columns to clean names ──────────────────
df.rename(columns={
    "visibility_km"               : "visibility",
    "air_quality_PM2.5"           : "pm25",
    "air_quality_Nitrogen_dioxide" : "nox"
}, inplace=True)

# ── Step 4: Create TRAFFIC score ───────────────────────────
# Higher humidity + higher wind = harder driving conditions
df["traffic"] = (df["humidity"] * 0.4 + df["wind_kph"] * 0.6).astype(int)

# ── Step 5: Create ACTION label ────────────────────────────
# action = 1 means "Reduce traffic" (dangerous condition)
# action = 0 means "Normal traffic"
#
# Rules (WHO + EU standards):
#   PM2.5 > 75  µg/m³  → dangerous pollution
#   visibility  < 5 km → dangerous fog
#   condition_text contains "fog" → foggy weather

def decide_action(row):
    if row["pm25"] > 75:
        return 1
    if row["visibility"] < 5:
        return 1
    if "fog" in str(row["condition_text"]).lower():
        return 1
    return 0

df["action"] = df.apply(decide_action, axis=1)

# ── Step 6: Keep only final columns ───────────────────────
df = df[["pm25", "visibility", "traffic", "nox", "action"]]

# ── Step 7: Round float columns ───────────────────────────
df["pm25"]       = df["pm25"].round(2)
df["visibility"] = df["visibility"].round(2)
df["nox"]        = df["nox"].round(2)

# ── Step 8: Save ──────────────────────────────────────────
df.to_csv("processed_weather.csv", index=False)

# ── Step 9: Print summary ─────────────────────────────────
print("=" * 45)
print("✅ processed_weather.csv created!")
print(f"   Total rows     : {len(df)}")
print(f"   Action=1 (bad) : {(df['action']==1).sum()}")
print(f"   Action=0 (ok)  : {(df['action']==0).sum()}")
print(f"   PM2.5 min/max  : {df['pm25'].min()} / {df['pm25'].max()}")
print(f"   Visibility min : {df['visibility'].min()} km")
print("=" * 45)
print("\nSample rows:")
print(df.head(6).to_string(index=False))
