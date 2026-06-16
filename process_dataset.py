import pandas as pd
import numpy as np

# ============================================================
# process_dataset.py — BEIJING MULTI-SITE AIR QUALITY VERSION
#
# Source: UCI "Beijing Multi-Site Air-Quality Data" Data Set
# (Beijing Municipal Environmental Monitoring Center,
#  March 2013 - February 2017, hourly readings)
#
# 3 monitoring stations -> 3 urban districts of ONE city (Beijing):
#
#   Industrial District  -> Gucheng   (West Beijing,  industrial area)
#   Residential District -> Dongsi    (Central Beijing, residential area)
#   Green District       -> Dingling  (North Beijing, suburban/forest - Ming Tombs)
#
# Raw columns used: PM2.5, PM10, NO2, CO, TEMP, RAIN, WSPM
#
# Derived fields (not present in raw dataset, computed here):
#   visibility_km : derived from PM2.5 + PM10 (particulate haze model)
#                    visibility = 30 / (1 + (PM2.5+PM10)/100), clipped [0.5, 30]
#   traffic       : derived from CO + NO2 (vehicle-emission proxy)
#                    traffic = 5 + 95 * (0.5*norm(CO) + 0.5*norm(NO2)), clipped [5,100]
#   condition     : derived from RAIN / WSPM / TEMP -> Rainy/Windy/Cold/Hot/Clear
#
# Outputs:
#   processed_weather.csv     -> training data for edge ML model
#                                 columns: pm25, visibility, traffic, nox, action
#   beijing_<District>.csv    -> per-district chronological data for sensor.py
# ============================================================

# Folder containing the 12 raw PRSA station CSV files
PRSA_FOLDER = "PRSA2017_Data_20130301-20170228/PRSA_Data_20130301-20170228"

STATION_FILES = {
    "Industrial District": (f"{PRSA_FOLDER}/PRSA_Data_Gucheng_20130301-20170228.csv",  "Gucheng, Beijing"),
    "Residential District": (f"{PRSA_FOLDER}/PRSA_Data_Dongsi_20130301-20170228.csv",  "Dongsi, Beijing"),
    "Green District":       (f"{PRSA_FOLDER}/PRSA_Data_Dingling_20130301-20170228.csv", "Dingling, Beijing"),
}

# Same reference thresholds used by edge_agent.py (base_threshold = 75.0)
PM25_ACTION_THRESHOLD        = 75.0
VISIBILITY_ACTION_THRESHOLD  = 5.0


def derive_visibility(pm25, pm10):
    """Particulate-driven haze model: more PM2.5+PM10 -> lower visibility."""
    raw = 30.0 / (1.0 + (pm25 + pm10) / 100.0)
    return float(np.clip(raw, 0.5, 30.0))


def derive_traffic(co, no2):
    """CO and NO2 are dominant vehicle-emission markers -> traffic proxy."""
    norm_co  = np.clip((co - 100) / (3000 - 100), 0, 1)
    norm_no2 = np.clip(no2 / 150.0, 0, 1)
    score = 5 + 95 * (0.5 * norm_co + 0.5 * norm_no2)
    return int(np.clip(score, 5, 100))


def derive_condition(rain, wspm, temp):
    if rain > 0:
        return "Rainy"
    if wspm > 4:
        return "Windy"
    if temp < 0:
        return "Cold"
    if temp > 25:
        return "Hot"
    return "Clear"


def main():
    all_frames = []

    for district, (filename, city) in STATION_FILES.items():
        print(f"[PROCESS] Loading {filename} -> {district} ({city})")
        df = pd.read_csv(filename)

        # Drop rows with missing core pollutant readings (PM2.5, NO2)
        before = len(df)
        df = df.dropna(subset=["PM2.5", "NO2"]).copy()
        print(f"[PROCESS]   Dropped {before - len(df)} rows with missing PM2.5/NO2")

        # Fill remaining gaps (small %) with column median
        for col in ["PM10", "CO", "TEMP", "RAIN", "WSPM"]:
            if df[col].isna().any():
                df[col] = df[col].fillna(df[col].median())

        df["visibility"] = [
            derive_visibility(p, p10) for p, p10 in zip(df["PM2.5"], df["PM10"])
        ]
        df["traffic"] = [
            derive_traffic(c, n) for c, n in zip(df["CO"], df["NO2"])
        ]
        df["condition"] = [
            derive_condition(r, w, t) for r, w, t in zip(df["RAIN"], df["WSPM"], df["TEMP"])
        ]

        out = pd.DataFrame({
            "district"  : district,
            "pm25"      : df["PM2.5"].round(2),
            "nox"       : df["NO2"].round(2),
            "visibility": [round(v, 2) for v in df["visibility"]],
            "traffic"   : df["traffic"],
            "condition" : df["condition"],
            "city"      : city,       # e.g. "Gucheng, Beijing"
            "country"   : "",          # blank — city already includes Beijing
            "year"      : df["year"],
            "month"     : df["month"],
            "day"       : df["day"],
            "hour"      : df["hour"],
        })
        out = out.reset_index(drop=True)

        out_path = f"beijing_{district.replace(' ', '_')}.csv"
        out.to_csv(out_path, index=False)
        print(f"[PROCESS]   -> {out_path} ({len(out)} rows)")
        print(
            f"[PROCESS]   PM2.5 mean={out['pm25'].mean():.1f} | "
            f"NOx mean={out['nox'].mean():.1f} | "
            f"Visibility mean={out['visibility'].mean():.1f}km | "
            f"Traffic mean={out['traffic'].mean():.1f}"
        )

        all_frames.append(out)
        print()

    # ── Combined training dataset for ML model ───────────────
    combined = pd.concat(all_frames, ignore_index=True)
    combined["action"] = (
        (combined["pm25"] > PM25_ACTION_THRESHOLD)
        | (combined["visibility"] < VISIBILITY_ACTION_THRESHOLD)
    ).astype(int)

    training = combined[["pm25", "visibility", "traffic", "nox", "action"]]
    training.to_csv("processed_weather.csv", index=False)

    print(f"[PROCESS] processed_weather.csv written: {len(training)} rows")
    print(f"[PROCESS] action=1 (HIGH/CRITICAL) fraction: {training['action'].mean():.3f}")
    print("[PROCESS] Mean feature values by action label:")
    print(training.groupby("action")[["pm25", "visibility", "traffic", "nox"]].mean())


if __name__ == "__main__":
    main()