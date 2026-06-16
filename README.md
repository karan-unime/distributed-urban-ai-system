# Urban Distributed Agentic System
### Multi-Layer Cloud-Fog-Edge System for Autonomous Traffic & Resource Management Based on Pollution Data

## Project Overview

A fully autonomous, multi-layer distributed agentic system that manages urban traffic **and** computational/network resources across the districts of a city, based on real-time air-pollution data. Each layer — Edge, Fog, and Cloud — runs its own autonomous agent with a **sense -> reason -> act -> learn** loop. No human input is required at any point: agents detect pollution conditions, decide on traffic actions, assign and redistribute resources (bandwidth, compute priority, sensor activity, reporting interval), and adapt their thresholds based on whether past decisions worked.

The three layers simulate a real Cloud-Fog-Edge computing architecture, all running on a single PC using Docker containers communicating via MQTT.

## Main Goal

Autonomously:
1. Reduce or close traffic in city districts when pollution (PM2.5, NOx) or visibility reaches dangerous levels.
2. Assign and coordinate computational resources (bandwidth, compute priority, active sensors, reporting frequency) across districts — shifting capacity toward districts in crisis and away from calm ones.
3. Do all of this through a closed agentic feedback loop (Edge -> Fog -> Cloud -> Fog -> Edge), with no human intervention.

## Architecture

```
CLOUD LAYER  (cloud.py)
  - Global policy (NORMAL / ALERT / EMERGENCY)
  - City-wide resource_plan: orchestrates bandwidth/compute/sensors
    across all districts based on hotspot level and avg PM2.5
  - Tracks city-wide statistics
  - Broadcasts policy + resource plan down to Fog/Edge

  MQTT publish: city/cloud/policy
  MQTT subscribe: city/fog/summary, city/decisions

FOG LAYER  (fog_coordinator.py)
  - Aggregates all 3 district decisions
  - Detects pollution hotspots (state machine: CALM -> WATCHFUL
    -> COORDINATING -> EMERGENCY)
  - Coordinates resources between districts: redistributes
    bandwidth/compute/sensors FROM safe districts TO endangered ones
  - Issues district-wide traffic commands (NORMAL / RESTRICT / EMERGENCY)

  MQTT publish: city/fog/commands, city/fog/summary
  MQTT subscribe: city/decisions

EDGE LAYER  (edge_agent.py)
  - 3 District Agents: Industrial District / Residential District / Green District
  - Each agent has an explicit goal ("Keep PM2.5 in <district> below
    safe threshold"), publishes a human-readable reasoning string,
    and assigns its own resources (sensors_active, bandwidth_limit,
    compute_priority, reporting_interval) based on severity
  - Reads PM2.5, NOx, visibility, traffic per district
  - Runs a Decision Tree ML model (honest 80/20 train/test split)
  - Subscribes to Fog commands and Cloud policy, and adapts its
    threshold/severity/resources accordingly (closed feedback loop)
  - learn(): tracks whether past decisions actually reduced PM2.5,
    and tightens its threshold if "Reduce traffic" isn't working

  MQTT publish: city/decisions
  MQTT subscribe: city/all, city/fog/commands, city/cloud/policy

SENSOR LAYER  (sensor.py)
  - Streams real hourly air-quality readings from the UCI Beijing
    Multi-Site Air Quality Data Set
  - 3 districts = 3 real Beijing monitoring stations (one city,
    different parts of the same urban area)

  MQTT publish: city/all
```

## Technologies Used

| Technology | Purpose |
|---|---|
| Python 3.11 | Main programming language |
| Docker + Docker Compose | Container orchestration |
| MQTT (Eclipse Mosquitto) | Inter-layer communication |
| Pandas | Dataset processing |
| Scikit-learn | Decision Tree ML model |
| Flask + SocketIO | Live admin dashboard |
| Chart.js | Live PM2.5 charts on dashboard |
| UCI Beijing Multi-Site Air Quality Data Set | Real-world pollution dataset |

## Dataset

Source: [UCI Machine Learning Repository — Beijing Multi-Site Air-Quality Data Set](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data)

Hourly air-quality and meteorological readings from 12 monitoring stations in Beijing, collected by the Beijing Municipal Environmental Monitoring Center, March 2013 - February 2017.

This project uses **3 of the 12 stations**, mapped to 3 districts of a single urban environment (Beijing):

| District | Beijing Station | Profile | Avg PM2.5 |
|---|---|---|---|
| Industrial District | Gucheng (West Beijing) | Industrial area, high pollution | ~84 µg/m³ |
| Residential District | Dongsi (Central Beijing) | Central residential area | ~85 µg/m³ |
| Green District | Dingling (North Beijing, Ming Tombs area) | Suburban / forest, lowest pollution | ~67 µg/m³ |

Raw columns used directly: `PM2.5`, `NO2` (= `nox`), `year/month/day/hour`.

Fields not present in the raw dataset are **derived** by `process_dataset.py`:

| Derived field | Formula | Reasoning |
|---|---|---|
| `visibility` (km) | `30 / (1 + (PM2.5 + PM10) / 100)`, clipped to [0.5, 30] | Higher particulate load -> lower visibility (haze model) |
| `traffic` (5-100) | `5 + 95 * (0.5*norm(CO) + 0.5*norm(NO2))` | CO and NO2 are dominant vehicle-emission markers -> traffic proxy |
| `condition` | Rainy / Windy / Cold / Hot / Clear, from `RAIN`/`WSPM`/`TEMP` | Display only |

Action labels follow the same WHO-style threshold used throughout the system: `action = 1` (reduce/close traffic) when `PM2.5 > 75` or `visibility < 5 km`; otherwise `action = 0` (normal conditions).

## Agent Decision Logic

Edge Agent — 4 severity levels

| PM2.5 (µg/m³) | Visibility | Severity | Decision |
|---|---|---|---|
| up to 35 | above 5km | LOW | Normal traffic |
| 35 to 75 | 2 to 5km | MEDIUM | Normal traffic |
| 75 to 150 | below 5km | HIGH | Reduce traffic |
| above 150 | below 2km | CRITICAL | Close road |

Each edge agent also publishes:
- `goal`: e.g. "Keep PM2.5 in Industrial District below safe threshold (75 µg/m³)"
- `reason`: e.g. "PM2.5=124.5 | Trend=RISING_FAST | Severity=HIGH | Threshold=75.0"
- `resource_assignment`: `{sensors_active, reporting_interval, compute_priority, bandwidth_limit}`

Fog Coordinator — Hotspot detection & resource coordination

| Condition | Command | Resource coordination |
|---|---|---|
| 2+ districts HIGH | RESTRICT — reduce to 30% flow | Affected districts get more bandwidth/compute/sensors; safe districts yield capacity |
| 2+ districts CRITICAL | EMERGENCY — close all roads | Affected districts get max resources (BW 60%, CPU HIGH, 5 sensors, 0.5s interval) |
| Fewer than threshold danger districts | NORMAL — no action | Equal resource distribution across all districts |

Cloud Orchestrator — Global policy & resource orchestration

| Condition | Policy | Global resource plan |
|---|---|---|
| Avg PM2.5 below 75 | NORMAL | Equal bandwidth (100 units each) |
| Avg PM2.5 75-150 or hotspot HIGH | ALERT | Affected districts get 70 BW / MEDIUM priority; safe districts drop to 30 |
| Avg PM2.5 above 150 or hotspot CRITICAL | EMERGENCY | Affected districts get 90 BW / HIGH priority / 5 sensors; safe districts drop to 15 |

## Agentic Feedback Loop

The system is a closed loop, not a one-way pipeline:

```
Sensor -> Edge Agents -> Fog Coordinator -> Cloud Orchestrator
              ^                  |                  |
              |__________________|__________________|
                 (city/fog/commands, city/cloud/policy)
```

- **Edge -> Fog**: edge agents publish PM2.5/NOx/severity/decision/resource_assignment.
- **Fog -> Cloud**: fog publishes hotspot level, affected districts, and its resource allocations.
- **Cloud -> Fog/Edge**: cloud publishes global policy (NORMAL/ALERT/EMERGENCY) and a city-wide resource plan.
- **Fog -> Edge**: fog publishes per-district commands and resource allocations.
- **Edge reacts**: edge agents subscribe to both `city/fog/commands` and `city/cloud/policy`, and adjust their severity, threshold, and resources accordingly — e.g. an EMERGENCY cloud policy tightens the adaptive threshold; a fog RESTRICT command on a district escalates its severity.

This closes the loop: decisions made at Edge influence Fog, Fog influences Cloud, and Cloud's global policy influences Edge again — all autonomously.

## Project Structure

```
DISTRIBUTED PROJECT/
├── Edge/
│   ├── edge_agent.py
│   ├── processed_weather.csv      (generated by process_dataset.py)
│   └── Dockerfile
├── Fog/
│   ├── fog_coordinator.py
│   └── Dockerfile
├── cloud/
│   ├── cloud.py
│   └── Dockerfile
├── sensor/
│   ├── sensor.py
│   ├── beijing_Industrial_District.csv   (generated by process_dataset.py)
│   ├── beijing_Residential_District.csv  (generated by process_dataset.py)
│   ├── beijing_Green_District.csv        (generated by process_dataset.py)
│   └── Dockerfile
├── dashboard/
│   ├── app.py
│   ├── Dockerfile
│   └── templates/
│       └── index.html
├── PRSA2017_Data_20130301-20170228/
│   └── PRSA_Data_20130301-20170228/
│       ├── PRSA_Data_Gucheng_20130301-20170228.csv
│       ├── PRSA_Data_Dongsi_20130301-20170228.csv
│       ├── PRSA_Data_Dingling_20130301-20170228.csv
│       └── ... (other 9 stations, unused)
├── docker-compose.yml
├── mosquitto.conf
├── process_dataset.py
└── evaluate.py
```

## How to Run

Prerequisites: Docker Desktop and Python 3.11 (with `pandas` and `numpy` installed: `pip install pandas numpy`).

**Step 1 — Get the dataset.**
Download the UCI Beijing Multi-Site Air Quality Data Set and place the extracted folder at the project root so that the 3 required station CSVs are reachable at:
`PRSA2017_Data_20130301-20170228/PRSA_Data_20130301-20170228/PRSA_Data_Gucheng_20130301-20170228.csv` (and the Dongsi / Dingling equivalents).

**Step 2 — Process the dataset.**

```bash
python process_dataset.py
```

This generates 4 files in the project root:
- `processed_weather.csv` — combined training data for the edge ML model
- `beijing_Industrial_District.csv`, `beijing_Residential_District.csv`, `beijing_Green_District.csv` — per-district streaming data

Move `processed_weather.csv` into `Edge/`, and the 3 `beijing_*.csv` files into `sensor/`.

**Step 3 — Start the system.**

```bash
docker-compose up --build
```

**Step 4 — Open the admin dashboard** at http://localhost:5000

**Step 5 — Stop the system.**

```bash
docker-compose down
```

### Demo Mode

`sensor.py` has a `DEMO_MODE` flag:
- `DEMO_MODE = True` (default): streaming starts in late November 2013, ~100 hours before each district's first major winter smog spike (PM2.5 > 150). Within roughly the first minute of running, PM2.5 crosses the HIGH/CRITICAL thresholds, and the fog/cloud resource-coordination behavior becomes visible on the dashboard — ideal for live demos.
- `DEMO_MODE = False`: streams the full 4-year record chronologically from March 2013, cycling back to the start once it reaches February 2017.

This flag only affects what `sensor.py` streams live; it has no effect on `evaluate.py`, which trains/evaluates on the full `processed_weather.csv` regardless.

## Admin Dashboard

The live dashboard at http://localhost:5000 shows the cloud policy and resource plan, a district-wide PM2.5 trend chart (all 3 districts + WHO limit line), three district cards (Gucheng/Dongsi/Dingling, Beijing) each with PM2.5/visibility/NOx/traffic, severity, decision, the agent's **goal** and **reason**, live resource badges (bandwidth/compute/sensors/interval), and a per-district PM2.5 history mini-chart. It also shows the fog coordinator's hotspot status and the cloud orchestrator's statistics, plus a live event log. Updates in real time via WebSocket.

## MQTT Topic Structure

| Topic | Publisher | Subscriber |
|---|---|---|
| city/all | Sensor | Edge agents |
| city/decisions | Edge agents | Fog, Cloud, Dashboard |
| city/fog/summary | Fog coordinator | Cloud, Dashboard |
| city/fog/commands | Fog coordinator | Edge agents |
| city/cloud/policy | Cloud orchestrator | Edge agents, Fog, Dashboard |

## Evaluation

`evaluate.py` trains/evaluates the edge ML model directly on `processed_weather.csv` (the combined Beijing dataset, ~100,800 rows), using an honest **80/20 train/test split** (`train_test_split(..., test_size=0.20, stratify=y)` — the model never sees test rows during training). It reports classification accuracy plus resource-management metrics (bandwidth escalations/reductions, compute escalations, escalation accuracy, bandwidth units saved).

```bash
python evaluate.py
```

| Metric | Baseline (fixed-rule, no ML/agent) | Agentic system |
|---|---|---|
| Detection accuracy | Fixed-rule, no learning | Decision Tree, evaluated on held-out 20% |
| Response time | Periodic / delayed | Real-time (per MQTT message) |
| Resource allocation | Static, equal across districts | Dynamic, shifted toward districts in crisis |
| Hotspot detections | None | Active, with consecutive-hotspot escalation |
| Road closures issued | None | Issued automatically when CRITICAL |

## Academic Context

Title: Urban Multilayer Distributed Agentic System for Autonomous Traffic and Resource Management Based on Real-World Pollution Data

Key concepts demonstrated: Cloud-Fog-Edge distributed computing, multi-agent autonomous systems with explicit goals/reasoning/learning, resource assignment and coordination among distributed elements, MQTT publish-subscribe communication, real-world dataset ML training with an honest train/test split, containerised microservices with Docker, and a fully closed agentic feedback loop with zero human intervention.