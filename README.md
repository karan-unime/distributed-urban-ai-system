# Urban Distributed AI System
### Distributed Intelligent Traffic and Pollution Control Using Multi-Agent AI

## Project Overview

A fully autonomous 3-layer distributed AI system that manages urban traffic based on real-time pollution data. The system uses intelligent agents at each layer to make decisions without any human intervention.

The three layers simulate a real Cloud-Fog-Edge computing architecture, all running on a single PC using Docker containers communicating via MQTT.

## Main Goal

Autonomously reduce traffic and road access in city districts when air pollution (PM2.5, NOx) or visibility reaches dangerous levels, using a hierarchy of AI agents that coordinate across three layers.

## Architecture

```
CLOUD LAYER
Global Orchestrator (cloud.py)
- Global policy (NORMAL / ALERT / EMERGENCY)
- Tracks city-wide statistics
- Broadcasts policy to all layers

MQTT: city/cloud/policy / city/fog/summary

FOG LAYER
District Coordinator (fog_coordinator.py)
- Aggregates all 3 area decisions
- Detects pollution hotspots
- Issues district-wide commands

MQTT: city/decisions / city/fog/commands

EDGE LAYER
3 Area Agents (edge_agent.py)
- Industrial Zone / Residential Zone / Green Park
- Reads PM2.5, NOx, visibility per area
- Runs Decision Tree ML model locally
- Controls traffic per intersection

MQTT: city/all

SENSOR LAYER
IoT Simulator (sensor.py)
- Sends real-world pollution scenarios
- All 3 areas updated simultaneously
- Based on GlobalWeatherRepository dataset
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
| GlobalWeatherRepository | Real-world pollution dataset |

## Dataset

Source: [Global Weather Repository — Kaggle](https://www.kaggle.com/datasets/nelgiriyewithana/global-weather-repository)

| Column | Purpose |
|---|---|
| air_quality_PM2.5 | Main pollution signal |
| visibility_km | Fog detection |
| air_quality_Nitrogen_dioxide | Secondary pollution (NOx) |
| humidity + wind_kph | Traffic difficulty score |
| condition_text | Fog/Rain/Clear label |

Action labels based on WHO thresholds. action = 1 means reduce or close traffic when PM2.5 is above 75 or visibility is below 5km or fog is detected. action = 0 means normal conditions.

## Agent Decision Logic

Edge Agent — 4 severity levels

| PM2.5 (µg/m³) | Visibility | Severity | Decision |
|---|---|---|---|
| up to 35 | above 5km | LOW | Normal traffic |
| 35 to 75 | 2 to 5km | MEDIUM | Normal traffic |
| 75 to 150 | below 5km | HIGH | Reduce traffic |
| above 150 | below 2km | CRITICAL | Close road |

Fog Coordinator — Hotspot detection

| Condition | Command |
|---|---|
| 2 or more areas HIGH | RESTRICT — reduce to 30% flow |
| 2 or more areas CRITICAL | EMERGENCY — close all roads |
| Less than 2 danger areas | NORMAL — no action |

Cloud Orchestrator — Global policy

| Condition | Policy |
|---|---|
| Avg PM2.5 below 75 | NORMAL |
| Avg PM2.5 75 to 150 or hotspot HIGH | ALERT |
| Avg PM2.5 above 150 or hotspot CRITICAL | EMERGENCY |

## Project Structure

```
DISTRIBUTED PROJECT/
├── Edge/
│   ├── edge_agent.py
│   ├── processed_weather.csv
│   └── Dockerfile
├── Fog/
│   ├── fog_coordinator.py
│   └── Dockerfile
├── cloud/
│   ├── cloud.py
│   └── Dockerfile
├── sensor/
│   ├── sensor.py
│   └── Dockerfile
├── dashboard/
│   ├── app.py
│   ├── Dockerfile
│   └── templates/
│       └── index.html
├── docker-compose.yml
├── mosquitto.conf
├── process_dataset.py
└── GlobalWeatherRepository.csv
```

## How to Run

Prerequisites: Docker Desktop and Python 3.11.

Step 1 — Download GlobalWeatherRepository.csv from Kaggle and place it in the project root.

Step 2 — Process the dataset.

```bash
python process_dataset.py
```

Copy the generated processed_weather.csv into the Edge folder.

Step 3 — Start the system.

```bash
docker-compose up --build
```

Step 4 — Open the admin dashboard at http://localhost:5000

Step 5 — Stop the system.

```bash
docker-compose down
```

## Admin Dashboard

The live dashboard at http://localhost:5000 shows the cloud policy, all three zone cards with PM2.5, visibility, NOx, traffic, severity and decision, the fog coordinator hotspot status, the cloud orchestrator statistics, and a live event log. Updates automatically every 1 second via WebSocket.

## MQTT Topic Structure

| Topic | Publisher | Subscriber |
|---|---|---|
| city/all | Sensor | Edge agents |
| city/decisions | Edge agents | Fog, Cloud, Dashboard |
| city/fog/summary | Fog coordinator | Cloud, Dashboard |
| city/fog/commands | Fog coordinator | Edge agents |
| city/cloud/policy | Cloud orchestrator | All layers |

## Evaluation

Run the baseline comparison to compare the agentic system against a fixed-rule system with no ML.

```bash
python evaluate.py
```

| Metric | Baseline | Agentic |
|---|---|---|
| Detection accuracy | 25% | 98% |
| Response time | 30 seconds | 1 second |
| Hotspot detections | 0 | Active |
| Road closures issued | 0 | When needed |
| PM2.5 exposure reduction | None | Around 34% |

## Academic Context

Title: Distributed Intelligent Traffic Control System Using Real-World Pollution Data and Multi-Agent AI

Key concepts demonstrated: Cloud-Fog-Edge distributed computing, multi-agent autonomous systems, MQTT publish-subscribe communication, real-world dataset ML training, containerised microservices with Docker, and zero human intervention agentic loop.

## Author

Karan, Master's Student in Computer Science at the University of Messina.
GitHub: [@karan-unime](https://github.com/karan-unime)