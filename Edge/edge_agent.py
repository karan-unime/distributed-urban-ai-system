import paho.mqtt.client as mqtt
import json
import time
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from datetime import datetime
from collections import deque

# ============================================================
# edge_agent.py  —  EDGE LAYER  —  Agentic System
#
# SENSE   — reads sensor data from MQTT every second
# REASON  — runs ML model + severity rules + memory
# ACT     — publishes decision + resource assignment
# LEARN   — adapts thresholds AND resources based on outcomes
#
# Resource Assignment (NEW):
#   Each agent autonomously assigns:
#     - sensors_active      : how many sensors are running
#     - reporting_interval  : seconds between reports
#     - compute_priority    : LOW / MEDIUM / HIGH
#     - bandwidth_limit     : % of bandwidth allocated
#
# Learning (ENHANCED):
#   Tracks whether past decisions actually reduced pollution.
#   If "Reduce traffic" keeps failing → escalates threshold.
# ============================================================

BROKER         = "mqtt"
PORT           = 1883
AREAS          = ["Industrial District", "Residential District", "Green District"]
SUB_TOPIC      = "city/all"
SUB_FOG_CMD    = "city/fog/commands"    # NEW: fog coordination commands
SUB_CLOUD_POL  = "city/cloud/policy"   # NEW: cloud global policy
PUB_TOPIC      = "city/decisions"

# ── Global policy received from cloud ────────────────────────
# Agents adapt their behaviour when cloud broadcasts a new policy
current_cloud_policy = {
    "level"        : "NORMAL",
    "pm25_limit"   : 75.0,
    "resource_plan": {},
}

# ── Fog coordination received from fog layer ──────────────────
current_fog_command = {
    "command"             : "NORMAL",
    "affected_areas"      : [],
    "resource_allocations": {},
}

# ── Train model ──────────────────────────────────────────────
print("[EDGE] Loading dataset...")
data = pd.read_csv("processed_weather.csv")

X = data[["pm25", "visibility", "traffic", "nox"]]
y = data["action"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

model = DecisionTreeClassifier(max_depth=5, random_state=42)
model.fit(X_train, y_train)

from sklearn.metrics import accuracy_score
test_acc = accuracy_score(y_test, model.predict(X_test))
print(f"[EDGE] Model trained on {len(X_train)} rows ✅")
print(f"[EDGE] Honest test accuracy (unseen 20%): {test_acc*100:.1f}%")
print(f"[EDGE] Managing zones: {AREAS}\n")


# ══════════════════════════════════════════════════════════════
# AGENT CLASS — one instance per zone
# ══════════════════════════════════════════════════════════════
class ZoneAgent:
    """
    Autonomous agent for one city zone.

    Goal       : keep PM2.5 below safe threshold
    Memory     : sliding window of last 10 readings
    Resources  : autonomously assigns sensors, bandwidth, compute
    Learning   : tracks decision outcomes, adapts threshold
    State      : NORMAL → WATCHFUL → ACTIVE → EMERGENCY
    """

    def __init__(self, zone_name):
        self.name               = zone_name
        self.state              = "NORMAL"
        self.memory             = deque(maxlen=10)
        self.decision_history   = deque(maxlen=20)
        self.action_outcomes    = deque(maxlen=20)
        self.consecutive_high   = 0
        self.base_threshold     = 75.0
        self.adaptive_threshold = 75.0
        self.total_decisions    = 0
        self.total_actions      = 0
        self.goal_violations    = 0
        self.created_at         = datetime.now().strftime("%H:%M:%S")
        self.last_pm25          = 0.0
        self.last_reason        = ""    # NEW: explanation of last decision
        self.last_decision      = "—"  # NEW: track for learn()

        # ── AGENT GOAL (NEW) ─────────────────────────────────
        # Explicit goal makes the agentic nature clear
        self.goal = f"Keep PM2.5 in {zone_name} below safe threshold (75 µg/m³)"

        # ── Resource state ────────────────────────────────────
        self.resources = {
            "sensors_active"    : 3,
            "reporting_interval": 1,
            "compute_priority"  : "LOW",
            "bandwidth_limit"   : 50,
        }

    # ── SENSE ─────────────────────────────────────────────────
    def sense(self, pm25, visibility, traffic, nox,
              city="—", country="—", condition="—"):
        self.memory.append(pm25)

        if pm25 > self.base_threshold:
            self.goal_violations  += 1
            self.consecutive_high += 1
        else:
            self.consecutive_high = max(0, self.consecutive_high - 1)

        return {
            "pm25": pm25, "visibility": visibility,
            "traffic": traffic, "nox": nox,
            "city": city, "country": country, "condition": condition
        }

    # ── REASON ────────────────────────────────────────────────
    def reason(self, reading):
        pm25       = reading["pm25"]
        visibility = reading["visibility"]
        traffic    = reading["traffic"]
        nox        = reading["nox"]

        # ML prediction
        input_df   = pd.DataFrame(
            [[pm25, visibility, traffic, nox]],
            columns=["pm25", "visibility", "traffic", "nox"]
        )
        ml_pred    = int(model.predict(input_df)[0])
        ml_proba   = model.predict_proba(input_df)[0]
        confidence = round(max(ml_proba) * 100, 1)

        trend    = self._get_trend()
        severity = self._classify_severity(pm25, visibility)

        # ── Build human-readable reason (NEW) ─────────────────
        reason_parts = [
            f"PM2.5={pm25:.1f} µg/m³",
            f"Trend={trend}",
            f"Severity={severity}",
            f"Threshold={self.adaptive_threshold:.1f}",
        ]

        # Agentic override: anticipate danger when trend is rising fast
        if trend == "RISING_FAST" and self.state == "WATCHFUL":
            if severity == "MEDIUM":
                severity = "HIGH"
                reason_parts.append("Override: RISING_FAST in WATCHFUL → escalated to HIGH")

        # ── Cloud policy awareness (NEW) ──────────────────────
        # If cloud set EMERGENCY policy, tighten threshold immediately
        cloud_level = current_cloud_policy.get("level", "NORMAL")
        cloud_limit = current_cloud_policy.get("pm25_limit", 75.0)
        if cloud_level == "EMERGENCY" and self.adaptive_threshold > cloud_limit:
            self.adaptive_threshold = cloud_limit
            reason_parts.append(f"Cloud EMERGENCY policy: threshold → {cloud_limit}")
        elif cloud_level == "ALERT" and self.adaptive_threshold > cloud_limit:
            self.adaptive_threshold = min(self.adaptive_threshold, cloud_limit)
            reason_parts.append(f"Cloud ALERT policy: threshold capped at {cloud_limit}")

        # ── Fog command awareness (NEW) ───────────────────────
        # If fog issued EMERGENCY for this zone, force close road
        fog_cmd     = current_fog_command.get("command", "NORMAL")
        fog_areas   = current_fog_command.get("affected_areas", [])
        fog_alloc   = current_fog_command.get("resource_allocations", {})

        if fog_cmd == "EMERGENCY" and self.name in fog_areas:
            severity = "CRITICAL"
            reason_parts.append("Fog EMERGENCY command: forced CRITICAL")
        elif fog_cmd == "RESTRICT" and self.name in fog_areas:
            if severity not in ["HIGH", "CRITICAL"]:
                severity = "HIGH"
                reason_parts.append("Fog RESTRICT command: escalated to HIGH")

        # Apply fog-allocated resources if available for this zone
        if self.name in fog_alloc:
            alloc = fog_alloc[self.name]
            self.resources["bandwidth_limit"]    = alloc.get("bandwidth",           self.resources["bandwidth_limit"])
            self.resources["compute_priority"]   = alloc.get("compute_priority",    self.resources["compute_priority"])
            self.resources["reporting_interval"] = alloc.get("reporting_interval",  self.resources["reporting_interval"])
            self.resources["sensors_active"]     = alloc.get("sensors_active",      self.resources["sensors_active"])
            reason_parts.append(f"Fog resource allocation applied: BW={alloc.get('bandwidth','?')}%")

        self._update_state(severity)

        # Apply adaptive learning
        self._adapt_threshold()

        # Never exceed cloud emergency limit
        cloud_limit = current_cloud_policy.get("pm25_limit", 75.0)
        self.adaptive_threshold = min(
            self.adaptive_threshold,
            cloud_limit
        )

        self._adapt_resources(severity)

        if ml_pred == 1 or severity in ["HIGH", "CRITICAL"]:
            decision = "Close road" if severity == "CRITICAL" else "Reduce traffic"
        else:
            decision = "Normal traffic"

        self.last_reason = " | ".join(reason_parts)
        return severity, decision, confidence, trend

    # ── ACT ───────────────────────────────────────────────────
    def act(self, reading, severity, decision, confidence, trend, client):
        self.total_decisions += 1
        self.decision_history.append(decision)
        if decision != "Normal traffic":
            self.total_actions += 1

        self.last_decision = decision

        payload = {
            "district"           : self.name,
            "decision"           : decision,
            "severity"           : severity,
            "pm25"               : reading["pm25"],
            "visibility"         : reading["visibility"],
            "traffic"            : reading["traffic"],
            "nox"                : reading["nox"],
            "city"               : reading.get("city", "—"),
            "country"            : reading.get("country", "—"),
            "condition"          : reading.get("condition", "—"),
            "trend"              : trend,
            "agent_state"        : self.state,
            "confidence"         : confidence,
            "adaptive_threshold" : round(self.adaptive_threshold, 1),
            "consecutive_high"   : self.consecutive_high,
            "memory_avg"         : round(sum(self.memory)/len(self.memory), 1) if self.memory else 0,
            "goal_violations"    : self.goal_violations,
            # AGENTIC: explicit goal and reasoning explanation
            "goal"               : self.goal,
            "reason"             : self.last_reason,
            "cloud_policy"       : current_cloud_policy.get("level", "NORMAL"),
            "fog_command"        : current_fog_command.get("command", "NORMAL"),
            "resource_assignment": {
                "sensors_active"    : self.resources["sensors_active"],
                "reporting_interval": self.resources["reporting_interval"],
                "compute_priority"  : self.resources["compute_priority"],
                "bandwidth_limit"   : self.resources["bandwidth_limit"],
            },
            "layer": "edge"
        }

        client.publish(PUB_TOPIC, json.dumps(payload))

        print(
            f"[EDGE | {self.name:18s}] "
            f"PM2.5={reading['pm25']:6.1f} | "
            f"State={self.state:9s} | "
            f"Severity={severity:8s} | "
            f"→ {decision} ({confidence}%) | "
            f"BW={self.resources['bandwidth_limit']}% "
            f"CPU={self.resources['compute_priority']}"
        )
        print(f"         Reason: {self.last_reason}")

    # ── LEARN ─────────────────────────────────────────────────
    def learn(self, prev_pm25, current_pm25, last_decision):
        """
        NEW: Outcome-based learning.

        Tracks whether past decisions actually reduced pollution.
        If "Reduce traffic" repeatedly fails to improve PM2.5,
        the agent escalates its base threshold — acting sooner next time.
        If pollution is improving, it relaxes threshold back toward WHO standard.
        """
        improved = current_pm25 < prev_pm25

        self.action_outcomes.append({
            "decision": last_decision,
            "improved": improved,
            "prev_pm25"   : round(prev_pm25, 1),
            "current_pm25": round(current_pm25, 1),
        })

        # Check last 5 "Reduce traffic" outcomes
        recent = list(self.action_outcomes)[-5:]
        reduce_ineffective = sum(
            1 for o in recent
            if o["decision"] == "Reduce traffic" and not o["improved"]
        )

        if reduce_ineffective >= 3:
            # Reduce traffic keeps failing → act more aggressively
            old = self.base_threshold
            self.base_threshold = max(50.0, self.base_threshold - 5.0)
            if self.base_threshold != old:
                print(
                    f"[EDGE | {self.name:18s}] "
                    f"⚡ LEARNING: base_threshold {old} → {self.base_threshold} "
                    f"(reduce_traffic ineffective {reduce_ineffective}/5)"
                )

        # If last 5 readings show consistent improvement, relax threshold
        consistent_improve = sum(1 for o in recent if o["improved"])
        if consistent_improve >= 4 and self.base_threshold < 75.0:
            old = self.base_threshold
            self.base_threshold = min(75.0, self.base_threshold + 2.0)
            print(
                f"[EDGE | {self.name:18s}] "
                f"✅ LEARNING: threshold relaxed {old} → {self.base_threshold}"
            )

    # ── INTERNAL HELPERS ──────────────────────────────────────
    def _adapt_resources(self, severity):
        """
        NEW: Autonomously assign resources based on severity.
        CRITICAL/HIGH zones get more sensors, bandwidth, and compute.
        Safe zones scale down to free resources for dangerous zones.
        """
        if severity == "CRITICAL":
            self.resources["sensors_active"]     = 5
            self.resources["reporting_interval"] = 0.5
            self.resources["compute_priority"]   = "HIGH"
            self.resources["bandwidth_limit"]    = 100
        elif severity == "HIGH":
            self.resources["sensors_active"]     = 4
            self.resources["reporting_interval"] = 1
            self.resources["compute_priority"]   = "MEDIUM"
            self.resources["bandwidth_limit"]    = 75
        elif severity == "MEDIUM":
            self.resources["sensors_active"]     = 3
            self.resources["reporting_interval"] = 1
            self.resources["compute_priority"]   = "LOW"
            self.resources["bandwidth_limit"]    = 50
        else:
            # LOW: scale down — yield resources to other zones
            self.resources["sensors_active"]     = 2
            self.resources["reporting_interval"] = 2
            self.resources["compute_priority"]   = "LOW"
            self.resources["bandwidth_limit"]    = 30

    def _adapt_threshold(self):
        if self.consecutive_high >= 5:
            self.adaptive_threshold = max(50.0, self.adaptive_threshold - 5.0)
        elif self.consecutive_high == 0:
            self.adaptive_threshold = min(
                self.base_threshold,
                self.adaptive_threshold + 1.0
            )

    def _get_trend(self):
        if len(self.memory) < 3:
            return "UNKNOWN"
        recent = list(self.memory)
        last3  = recent[-3:]
        if last3[-1] > last3[0] * 1.3:    return "RISING_FAST"
        elif last3[-1] > last3[0] * 1.1:  return "RISING"
        elif last3[-1] < last3[0] * 0.7:  return "FALLING_FAST"
        elif last3[-1] < last3[0] * 0.9:  return "FALLING"
        else:                              return "STABLE"

    def _classify_severity(self, pm25, visibility):
        thresh = self.adaptive_threshold
        if pm25 > 150 or visibility < 2:      return "CRITICAL"
        elif pm25 > thresh or visibility < 5: return "HIGH"
        elif pm25 > thresh * 0.5:             return "MEDIUM"
        else:                                 return "LOW"

    def _update_state(self, severity):
        if severity == "CRITICAL":
            self.state = "EMERGENCY"
        elif severity == "HIGH":
            self.state = "ACTIVE"
        elif severity == "MEDIUM" or self.consecutive_high > 0:
            self.state = "WATCHFUL"
        else:
            self.state = "NORMAL"


# ── Create one agent per zone ────────────────────────────────
agents = {zone: ZoneAgent(zone) for zone in AREAS}
print("[EDGE] Agents created:")
for name, agent in agents.items():
    print(f"  {name:20s} | State={agent.state} | Threshold={agent.adaptive_threshold} | "
          f"Resources={agent.resources}")
print()

# ── MQTT ─────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[EDGE] Connected to MQTT broker ✅")
        client.subscribe(SUB_TOPIC)
        client.subscribe(SUB_FOG_CMD)    # NEW: listen to fog coordination
        client.subscribe(SUB_CLOUD_POL)  # NEW: listen to cloud policy
        print(f"[EDGE] Subscribed to: {SUB_TOPIC}, {SUB_FOG_CMD}, {SUB_CLOUD_POL}")
        print("[EDGE] All agents running — sense → reason → act → learn")
        print("[EDGE] Feedback loop ACTIVE: Edge ← Fog ← Cloud\n")
    else:
        print(f"[EDGE] Connection failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        topic = msg.topic

        # =====================================================
        # CLOUD → EDGE
        # =====================================================
        if topic == SUB_CLOUD_POL:

            global current_cloud_policy
            current_cloud_policy.update(payload)

            print(
                f"[EDGE] Cloud Policy Updated → "
                f"{payload.get('level', 'NORMAL')}"
            )
            return

        # =====================================================
        # FOG → EDGE
        # =====================================================
        if topic == SUB_FOG_CMD:

            global current_fog_command
            current_fog_command.update(payload)

            print(
                f"[EDGE] Fog Command Updated → "
                f"{payload.get('command', 'NORMAL')}"
            )
            return

        # =====================================================
        # SENSOR → EDGE
        # =====================================================
        zone = payload.get("district")

        if zone not in AREAS:
            return

        agent = agents[zone]
        
        prev_pm25 = agent.last_pm25
        prev_dec  = agent.last_decision

        # ── SENSE ──
        reading = agent.sense(
            float(payload.get("pm25",        0)),
            float(payload.get("visibility",  10)),
            float(payload.get("traffic",     30)),
            float(payload.get("nox",          0)),
            payload.get("city",      "—"),
            payload.get("country",   "—"),
            payload.get("condition", "—")
        )

        prev_pm25 = agent.last_pm25
        prev_dec  = agent.last_decision

        # ── REASON ──
        severity, decision, confidence, trend = agent.reason(reading)

        # ── ACT ──
        agent.act(reading, severity, decision, confidence, trend, client)

        # ── LEARN ──
        if prev_pm25 > 0:
            agent.learn(prev_pm25, reading["pm25"], prev_dec)

        # Save for next cycle
        agent.last_pm25 = reading["pm25"]

    except Exception as e:
        print(f"[EDGE] Error: {e}")

# ── Start ─────────────────────────────────────────────────────
print("[EDGE] Connecting to broker...")
time.sleep(3)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()