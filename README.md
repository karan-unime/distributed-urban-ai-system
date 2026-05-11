# 🏙 Urban Distributed AI System
### Distributed Intelligent Traffic & Pollution Control Using Multi-Agent AI

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-purple)
![ML](https://img.shields.io/badge/ML-DecisionTree-orange)
![Flask](https://img.shields.io/badge/Dashboard-Flask-green)

> Master's Thesis Project — Distributed Systems  
> University of Messina — 9 CFU

---

## 📌 Project Overview

A fully autonomous **3-layer distributed AI system** that manages urban traffic
based on real-time pollution data. The system uses intelligent agents at each
layer to make decisions **without any human intervention**.

The three layers simulate a real **Cloud-Fog-Edge** computing architecture,
all running on a single PC using Docker containers communicating via MQTT.

---

## 🎯 Main Goal

> Autonomously reduce traffic and road access in city districts when
> air pollution (PM2.5, NOx) or visibility reaches dangerous levels —
> using a hierarchy of AI agents that coordinate across three layers.

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────┐
│                   CLOUD LAYER                        │
│         Global Orchestrator (cloud.py)               │
│   • Global policy (NORMAL / ALERT / EMERGENCY)       │
│   • Tracks city-wide statistics                      │
│   • Broadcasts policy to all layers                  │
└──────────────────┬──────────────────────────────────┘
                   │ MQTT: city/cloud/policy
                   │ MQTT: city/fog/summary
┌──────────────────▼──────────────────────────────────┐
│                    FOG LAYER                         │
│         District Coordinator (fog_coordinator.py)    │
│   • Aggregates all 3 area decisions                  │
│   • Detects pollution hotspots                       │
│   • Issues district-wide commands                    │
└──────────────────┬──────────────────────────────────┘
                   │ MQTT: city/decisions
                   │ MQTT: city/fog/commands
┌──────────────────▼──────────────────────────────────┐
│                   EDGE LAYER                         │
│          3 Area Agents (edge_agent.py)               │
│   • Area1 / Area2 / Area3                            │
│   • Reads PM2.5, NOx, visibility per area            │
│   • Runs Decision Tree ML model locally              │
│   • Controls traffic per intersection                │
└──────────────────┬──────────────────────────────────┘
                   │ MQTT: city/all
┌──────────────────▼──────────────────────────────────┐
│                 SENSOR LAYER                         │
│            IoT Simulator (sensor.py)                 │
│   • Sends real-world pollution scenarios             │
│   • All 3 areas updated simultaneously               │
│   • Based on GlobalWeatherRepository dataset         │
└─────────────────────────────────────────────────────┘
```

---

## 🧠 Technologies Used

| Technology | Purpose |
|---|---|
| Python 3.11 | Main programming language |
| Docker + Docker Compose | Container orchestration |
| MQTT (Eclipse Mosquitto) | Inter-layer communication |
| Pandas | Dataset processing |
| Scikit-learn | Decision Tree ML model |
| Flask + SocketIO | Live admin dashboard |
| GlobalWeatherRepository | Real-world pollution dataset |

---

## 📊 Dataset

**Source:** [Global Weather Repository — Kaggle](https://www.kaggle.com/datasets/nelgiriyewithana/global-weather-repository)

**Columns used:**

| Column | Purpose |
|---|---|
| air_quality_PM2.5 | Main pollution signal |
| visibility_km | Fog detection |
| air_quality_Nitrogen_dioxide | Secondary pollution (NOx) |
| humidity + wind_kph | Traffic difficulty score |
| condition_text | Fog/Rain/Clear label |

**Action labels (WHO thresholds):**
- `action = 1` (Reduce/Close) → PM2.5 > 75 OR visibility < 5km OR fog
- `action = 0` (Normal) → all conditions acceptable

---

## 🤖 Agent Decision Logic

### Edge Agent — 4 severity levels

| PM2.5 (µg/m³) | Visibility | Severity | Decision |
|---|---|---|---|
| ≤ 35 | > 5km | LOW | Normal traffic |
| 35–75 | 2–5km | MEDIUM | Normal traffic |
| 75–150 | < 5km | HIGH | Reduce traffic |
| > 150 | < 2km | CRITICAL | Close road |

### Fog Coordinator — Hotspot detection

| Condition | Command |
|---|---|
| 2+ areas HIGH | RESTRICT — reduce to 30% flow |
| 2+ areas CRITICAL | EMERGENCY — close all roads |
| < 2 danger areas | NORMAL — no action |

### Cloud Orchestrator — Global policy

| Condition | Policy |
|---|---|
| Avg PM2.5 < 75 | NORMAL |
| Avg PM2.5 75–150 OR hotspot HIGH | ALERT |
| Avg PM2.5 > 150 OR hotspot CRITICAL | EMERGENCY |

---

## 📁 Project Structure

```
DISTRIBUTED PROJECT/
├── Edge/
│   ├── edge_agent.py          ← Edge layer — all 3 areas
│   ├── processed_weather.csv  ← processed dataset
│   └── Dockerfile
├── Fog/
│   ├── fog_coordinator.py     ← Fog layer — district coordinator
│   └── Dockerfile
├── cloud/
│   ├── cloud.py               ← Cloud layer — global orchestrator
│   └── Dockerfile
├── sensor/
│   ├── sensor.py              ← IoT sensor simulator
│   └── Dockerfile
├── dashboard/
│   ├── app.py                 ← Flask + SocketIO admin panel
│   ├── Dockerfile
│   └── templates/
│       └── index.html         ← Live dashboard UI
├── docker-compose.yml         ← Orchestrates all containers
├── mosquitto.conf             ← MQTT broker config
├── process_dataset.py         ← Dataset processing script
└── GlobalWeatherRepository.csv ← Raw dataset (download from Kaggle)
```

---

## 🚀 How to Run

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.11 (for dataset processing only)

### Step 1 — Download the dataset
Download from Kaggle and place in project root:
```
GlobalWeatherRepository.csv
```

### Step 2 — Process the dataset
```bash
python process_dataset.py
```
Copy the generated `processed_weather.csv` into the `Edge/` folder.

### Step 3 — Start the system
```bash
docker-compose up --build
```

### Step 4 — Open the admin dashboard
```
http://localhost:5000
```

### Step 5 — Stop the system
```bash
docker-compose down
```

---

## 📺 Admin Dashboard

The live dashboard at `http://localhost:5000` shows:

- **Cloud Policy** — NORMAL / ALERT / EMERGENCY
- **3 Area Cards** — PM2.5, visibility, NOx, traffic, severity, decision
- **Fog Coordinator** — hotspot level, command, affected areas
- **Cloud Orchestrator** — total messages, reduces, closures, hotspots
- **Live Event Log** — all layer events in real time

Updates automatically every 1 second via WebSocket.

---

## 📡 MQTT Topic Structure

| Topic | Publisher | Subscriber |
|---|---|---|
| `city/all` | Sensor | Edge agents |
| `city/decisions` | Edge agents | Fog, Cloud, Dashboard |
| `city/fog/summary` | Fog coordinator | Cloud, Dashboard |
| `city/fog/commands` | Fog coordinator | Edge agents |
| `city/cloud/policy` | Cloud orchestrator | All layers |

---

## 📈 Evaluation

Run the baseline comparison:
```bash
python evaluate.py
```

Compares **Agentic System** vs **Baseline** (fixed 30s green light, no ML):

| Metric | Baseline | Agentic | Improvement |
|---|---|---|---|
| Avg PM2.5 response time | — | — | — |
| Hotspot detections | 0 | ✓ | — |
| Road closures issued | 0 | ✓ | — |
| Autonomous decisions | 0 | ✓ | — |

*(Run evaluate.py to fill in real numbers)*

---

## 🎓 Academic Context

**Title:** Distributed Intelligent Traffic Control System Using Real-World
Pollution Data and Multi-Agent AI

**Key concepts demonstrated:**
- Cloud-Fog-Edge distributed computing
- Multi-agent autonomous systems
- MQTT publish/subscribe communication
- Real-world dataset ML training
- Containerised microservices (Docker)
- Zero human intervention agentic loop

---

## 👤 Author

**Karan** — Master's Student, Computer Science  
University of Messina  
GitHub: [@karan-unime](https://github.com/karan-unime)
