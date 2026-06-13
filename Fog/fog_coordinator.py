import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
from collections import deque

# ============================================================
# fog_coordinator.py  —  FOG LAYER  —  Agentic Coordinator
#
# SENSE   — receives edge agent decisions via MQTT
# REASON  — detects hotspots, analyses district trends
# ACT     — issues coordinated district commands
#           + redistributes resources between zones (NEW)
# LEARN   — adapts escalation threshold based on hotspot history
#
# Resource Coordination (NEW):
#   The fog agent redistributes bandwidth, compute priority,
#   and sensor intervals across zones — shifting capacity
#   FROM safe zones TO endangered zones autonomously.
#
# Published to:
#   city/fog/commands  — per-zone resource allocations + commands
#   city/fog/summary   — district summary to cloud
# ============================================================

BROKER        = "mqtt"
PORT          = 1883
AREAS         = ["Industrial Zone", "Residential Zone", "Green Park"]
SUB_DECISIONS = "city/decisions"
PUB_COMMANDS  = "city/fog/commands"
PUB_SUMMARY   = "city/fog/summary"

TOTAL_BANDWIDTH = 150   # total bandwidth units shared across all zones


# ══════════════════════════════════════════════════════════════
# FOG AGENT — district-level autonomous coordinator
# ══════════════════════════════════════════════════════════════
class FogAgent:
    def __init__(self):
        self.state                 = "CALM"
        self.hotspot_history       = deque(maxlen=20)
        self.district_state        = {
            a: {"pm25": 0, "visibility": 10, "traffic": 0, "nox": 0,
                "severity": "LOW", "decision": "Normal traffic",
                "agent_state": "NORMAL", "trend": "UNKNOWN",
                "resource_assignment": {}}
            for a in AREAS
        }
        self.total_hotspots        = 0
        self.consecutive_hotspots  = 0
        self.goal_violations       = 0
        self.escalation_threshold  = 2
        self.commands_issued       = 0

        # NEW: fog-level resource allocation per zone
        self.resource_allocations  = {
            a: {"bandwidth": 50, "compute_priority": "LOW",
                "reporting_interval": 1, "sensors_active": 3}
            for a in AREAS
        }

    # ── SENSE ─────────────────────────────────────────────────
    def sense(self, payload):
        area = payload.get("district")
        if area not in AREAS:
            return False
        self.district_state[area].update({
            "pm25"               : payload.get("pm25",              0),
            "visibility"         : payload.get("visibility",         10),
            "traffic"            : payload.get("traffic",            0),
            "nox"                : payload.get("nox",                0),
            "severity"           : payload.get("severity",           "LOW"),
            "decision"           : payload.get("decision",           "Normal traffic"),
            "agent_state"        : payload.get("agent_state",        "NORMAL"),
            "trend"              : payload.get("trend",              "UNKNOWN"),
            "resource_assignment": payload.get("resource_assignment", {}),
        })
        return True

    # ── REASON ────────────────────────────────────────────────
    def reason(self):
        severities = {a: self.district_state[a]["severity"] for a in AREAS}
        trends     = {a: self.district_state[a]["trend"]    for a in AREAS}

        danger   = [a for a, s in severities.items() if s in ["HIGH", "CRITICAL"]]
        critical = [a for a, s in severities.items() if s == "CRITICAL"]

        avg_pm25 = round(sum(self.district_state[a]["pm25"] for a in AREAS) / len(AREAS), 2)
        avg_nox  = round(sum(self.district_state[a]["nox"]  for a in AREAS) / len(AREAS), 2)

        if avg_pm25 > 75:
            self.goal_violations += 1

        threshold   = self.escalation_threshold
        rising_fast = sum(1 for t in trends.values() if t == "RISING_FAST")

        if rising_fast >= 2 and self.state in ["WATCHFUL", "COORDINATING"]:
            threshold = 1

        if len(critical) >= 2:
            hotspot, level = True, "CRITICAL"
            affected = critical
        elif len(danger) >= threshold:
            hotspot, level = True, "HIGH"
            affected = danger
        else:
            hotspot, level = False, "LOW"
            affected = []

        if hotspot:
            self.consecutive_hotspots += 1
            self.total_hotspots       += 1
            self.hotspot_history.append({
                "time" : datetime.now().strftime("%H:%M:%S"),
                "level": level, "areas": affected
            })
            if self.consecutive_hotspots >= 3:
                self.escalation_threshold = 1
        else:
            self.consecutive_hotspots = 0
            self.escalation_threshold = 2

        return hotspot, affected, level, avg_pm25, avg_nox

    # ── RESOURCE COORDINATION (NEW) ───────────────────────────
    def _coordinate_resources(self, affected, level):
        """
        Redistribute district resources between zones autonomously.

        Logic:
          - Endangered zones (in affected) get the most bandwidth,
            highest compute, and fastest reporting.
          - Safe zones yield resources to free capacity for crisis zones.
          - Total bandwidth stays within TOTAL_BANDWIDTH budget.

        This implements the 'resource assignment and coordination
        among elements' requirement of the system description.
        """
        safe_zones = [a for a in AREAS if a not in affected]

        if level == "CRITICAL":
            # Crisis zones: max resources
            for area in affected:
                self.resource_allocations[area] = {
                    "bandwidth"          : 60,
                    "compute_priority"   : "HIGH",
                    "reporting_interval" : 0.5,
                    "sensors_active"     : 5,
                }
            # Safe zones: minimal — give bandwidth to crisis zones
            for area in safe_zones:
                self.resource_allocations[area] = {
                    "bandwidth"          : 15,
                    "compute_priority"   : "LOW",
                    "reporting_interval" : 3,
                    "sensors_active"     : 2,
                }

        elif level == "HIGH":
            for area in affected:
                self.resource_allocations[area] = {
                    "bandwidth"          : 50,
                    "compute_priority"   : "MEDIUM",
                    "reporting_interval" : 1,
                    "sensors_active"     : 4,
                }
            for area in safe_zones:
                self.resource_allocations[area] = {
                    "bandwidth"          : 25,
                    "compute_priority"   : "LOW",
                    "reporting_interval" : 2,
                    "sensors_active"     : 3,
                }

        else:
            # Normal: equal distribution
            for area in AREAS:
                self.resource_allocations[area] = {
                    "bandwidth"          : 50,
                    "compute_priority"   : "LOW",
                    "reporting_interval" : 1,
                    "sensors_active"     : 3,
                }

        # Log total bandwidth usage
        total_bw = sum(v["bandwidth"] for v in self.resource_allocations.values())
        print(
            f"[FOG] Resource coordination | Level={level} | "
            f"Total BW used: {total_bw}/{TOTAL_BANDWIDTH * len(AREAS) // 3}"
        )
        for area, alloc in self.resource_allocations.items():
            tag = "⚠" if area in affected else "✓"
            print(
                f"[FOG]   {tag} {area:20s} | "
                f"BW={alloc['bandwidth']:3d}% | "
                f"CPU={alloc['compute_priority']:6s} | "
                f"Sensors={alloc['sensors_active']} | "
                f"Interval={alloc['reporting_interval']}s"
            )

        return self.resource_allocations

    # ── ACT ───────────────────────────────────────────────────
    def act(self, client, hotspot, affected, level, avg_pm25, avg_nox):
        now = datetime.now().strftime("%H:%M:%S")
        self._update_state(hotspot, level)

        # Build traffic command
        if level == "CRITICAL":
            command = {
                "command"      : "EMERGENCY",
                "action"       : "Close all roads in affected zones",
                "affected_areas": affected
            }
        elif level == "HIGH":
            command = {
                "command"      : "RESTRICT",
                "action"       : "Reduce traffic to 30% in affected zones",
                "affected_areas": affected
            }
        else:
            command = {
                "command"      : "NORMAL",
                "action"       : "Normal operations",
                "affected_areas": []
            }

        self.commands_issued += 1

        # NEW: coordinate resources across zones
        allocations = self._coordinate_resources(affected, level)

        # Print summary
        if hotspot:
            print(f"\n{'='*60}")
            print(f"[FOG] HOTSPOT {level} at {now}")
            print(f"[FOG] State={self.state} | Zones={affected}")
            print(f"[FOG] Avg PM2.5={avg_pm25} | Consecutive={self.consecutive_hotspots}")
            print(f"[FOG] Threshold={self.escalation_threshold} zones | → {command['action']}")
            print(f"{'='*60}\n")
        else:
            print(
                f"[FOG] District OK | State={self.state} | "
                f"Avg PM2.5={avg_pm25} | Avg NOx={avg_nox}"
            )

        # Publish commands + resource allocations to edge layer
        client.publish(PUB_COMMANDS, json.dumps({
            "timestamp"          : now,
            "hotspot"            : hotspot,
            "hotspot_level"      : level,
            "fog_command"        : command,
            "agent_state"        : self.state,
            "resource_allocations": allocations,   # NEW
            "layer"              : "fog"
        }))

        # Publish summary to cloud + dashboard
        client.publish(PUB_SUMMARY, json.dumps({
            "timestamp"               : now,
            "avg_pm25"                : avg_pm25,
            "avg_nox"                 : avg_nox,
            "hotspot"                 : hotspot,
            "hotspot_level"           : level,
            "affected_areas"          : affected,
            "fog_command"             : command["command"],
            "agent_state"             : self.state,
            "total_hotspots"          : self.total_hotspots,
            "consecutive_hotspots"    : self.consecutive_hotspots,
            "escalation_threshold"    : self.escalation_threshold,
            "goal_violations"         : self.goal_violations,
            "area_severities"         : {a: self.district_state[a]["severity"] for a in AREAS},
            "area_trends"             : {a: self.district_state[a]["trend"]    for a in AREAS},
            "resource_allocations"    : allocations,   # NEW
            "layer"                   : "fog"
        }))

    def _update_state(self, hotspot, level):
        if level == "CRITICAL":
            self.state = "EMERGENCY"
        elif level == "HIGH":
            self.state = "COORDINATING"
        elif self.consecutive_hotspots > 0:
            self.state = "WATCHFUL"
        else:
            self.state = "CALM"


# ── Create fog agent ─────────────────────────────────────────
fog_agent = FogAgent()

# ── MQTT ─────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[FOG] Connected to MQTT broker ✅")
        client.subscribe(SUB_DECISIONS)
        print(f"[FOG] Fog agent active | State={fog_agent.state}")
        print("[FOG] sense → reason → act (+ resource coordination)\n")
    else:
        print(f"[FOG] Connection failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if payload.get("layer") == "fog":
            return

        if not fog_agent.sense(payload):
            return

        print(
            f"[FOG] Received from {payload.get('district'):18s} | "
            f"PM2.5={payload.get('pm25', 0):6.1f} | "
            f"AgentState={payload.get('agent_state', '?'):9s} | "
            f"Trend={payload.get('trend', '?')} | "
            f"BW={payload.get('resource_assignment', {}).get('bandwidth_limit', '?')}%"
        )

        hotspot, affected, level, avg_pm25, avg_nox = fog_agent.reason()
        fog_agent.act(client, hotspot, affected, level, avg_pm25, avg_nox)

    except Exception as e:
        print(f"[FOG] Error: {e}")


print("[FOG] Fog Coordinator Agent starting...")
print(f"[FOG] Monitoring zones: {AREAS}")
print("[FOG] Agentic mode: sense → reason → act (resource coordination)\n")
time.sleep(4)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()