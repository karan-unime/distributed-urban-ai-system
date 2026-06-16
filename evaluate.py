import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score
)
from datetime import datetime
from collections import deque

# ============================================================
# evaluate.py — Full System Evaluation
#
# Evaluates:
#   1. ML model accuracy (80/20 train/test split)
#   2. Baseline vs Agentic system comparison
#   3. NEW: Resource assignment effectiveness
#      - How much bandwidth is saved in safe zones?
#      - How many times were resources correctly escalated?
#      - Learning: did threshold adaptation trigger?
# ============================================================

print("=" * 65)
print("  URBAN DISTRIBUTED AI SYSTEM")
print("  With Resource Assignment & Coordination Metrics")
print("=" * 65)
print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 65)

# ── Load dataset ─────────────────────────────────────────────
print("\n[1] Loading dataset...")
df = pd.read_csv("processed_weather.csv")
print(f"    Total rows: {len(df)}")
print(f"    Action=1 (dangerous): {(df['action']==1).sum()} rows")
print(f"    Action=0 (normal):    {(df['action']==0).sum()} rows")

# ── Train/Test Split ─────────────────────────────────────────
print("\n[2] Splitting dataset — 80% train / 20% test...")
X = df[["pm25", "visibility", "traffic", "nox"]]
y = df["action"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

print(f"    Training set : {len(X_train)} rows  ({len(X_train)/len(df)*100:.1f}%)")
print(f"    Test set     : {len(X_test)} rows  ({len(X_test)/len(df)*100:.1f}%)")

# ── Train model ───────────────────────────────────────────────
print("\n[3] Training Decision Tree on TRAINING SET ONLY...")
model = DecisionTreeClassifier(max_depth=5, random_state=42)
model.fit(X_train, y_train)
print(f"    Tree depth: {model.get_depth()} levels ✅")

# ── Evaluate on test set ──────────────────────────────────────
print("\n[4] Evaluating on TEST SET (unseen data)...")
y_pred     = model.predict(X_test)
y_prob     = model.predict_proba(X_test)[:, 1]

test_acc   = accuracy_score(y_test, y_pred)
auc        = roc_auc_score(y_test, y_prob)

cm         = confusion_matrix(y_test, y_pred)
tn, fp, fn, tp = cm.ravel()

precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

print(f"    Test accuracy : {test_acc*100:.2f}%")
print(f"    Precision     : {precision*100:.2f}%")
print(f"    Recall        : {recall*100:.2f}%")
print(f"    F1 Score      : {f1*100:.2f}%")
print(f"    ROC-AUC Score : {auc*100:.2f}%")

print("\n    Confusion Matrix:")
print(cm)

print(f"\n    True Negative : {tn}")
print(f"    False Positive: {fp}")
print(f"    False Negative: {fn}")
print(f"    True Positive : {tp}")


# ── Helpers ───────────────────────────────────────────────────
def get_severity(pm25, visibility):
    if pm25 > 150 or visibility < 2:  return "CRITICAL"
    elif pm25 > 75 or visibility < 5: return "HIGH"
    elif pm25 > 35:                   return "MEDIUM"
    else:                             return "LOW"

def get_edge_resources(severity):
    """Mirrors _adapt_resources() in edge_agent.py."""
    if severity == "CRITICAL":
        return {"sensors_active": 5, "reporting_interval": 0.5,
                "compute_priority": "HIGH",   "bandwidth_limit": 100}
    elif severity == "HIGH":
        return {"sensors_active": 4, "reporting_interval": 1,
                "compute_priority": "MEDIUM", "bandwidth_limit": 75}
    elif severity == "MEDIUM":
        return {"sensors_active": 3, "reporting_interval": 1,
                "compute_priority": "LOW",    "bandwidth_limit": 50}
    else:
        return {"sensors_active": 2, "reporting_interval": 2,
                "compute_priority": "LOW",    "bandwidth_limit": 30}

def get_fog_resources(severity, is_affected):
    """Mirrors _coordinate_resources() in fog_coordinator.py."""
    if is_affected:
        if severity == "CRITICAL":
            return {"bandwidth": 60, "compute_priority": "HIGH",
                    "reporting_interval": 0.5, "sensors_active": 5}
        else:
            return {"bandwidth": 50, "compute_priority": "MEDIUM",
                    "reporting_interval": 1,   "sensors_active": 4}
    else:
        if severity == "CRITICAL":
            return {"bandwidth": 15, "compute_priority": "LOW",
                    "reporting_interval": 3,   "sensors_active": 2}
        else:
            return {"bandwidth": 25, "compute_priority": "LOW",
                    "reporting_interval": 2,   "sensors_active": 3}


# ── Baseline system ───────────────────────────────────────────
print("\n[5] Running BASELINE system on test set...")
baseline_preds = []
for _, row in X_test.iterrows():
    if row["visibility"] < 2:
        baseline_preds.append(1)
    else:
        baseline_preds.append(0)

baseline_preds  = np.array(baseline_preds)
base_acc        = accuracy_score(y_test, baseline_preds)
base_cm         = confusion_matrix(y_test, baseline_preds)
base_tn, base_fp, base_fn, base_tp = base_cm.ravel()
base_precision  = base_tp/(base_tp+base_fp) if (base_tp+base_fp)>0 else 0
base_recall     = base_tp/(base_tp+base_fn) if (base_tp+base_fn)>0 else 0
base_f1         = 2*base_precision*base_recall/(base_precision+base_recall) if (base_precision+base_recall)>0 else 0


# ── Agentic + Resource simulation ────────────────────────────
print("[6] Running AGENTIC system with resource simulation on test set...")

agent_reduces     = 0
agent_closes      = 0
hotspot_sim       = 0

# Resource tracking (NEW)
bw_escalations        = 0   # times bandwidth was increased for a zone
bw_reductions         = 0   # times bandwidth was reduced (freeing for others)
compute_escalations   = 0   # times compute_priority became MEDIUM or HIGH
correct_escalations   = 0   # escalation where severity was truly HIGH/CRITICAL
total_bw_saved        = 0   # bandwidth units saved vs always-on baseline

# Learning simulation (NEW)
learning_triggers     = 0
memory                = deque(maxlen=10)
action_outcomes       = deque(maxlen=20)
base_threshold        = 75.0
prev_pm25             = 0.0

# Simulate rows as if streaming through 3-zone system
district_buf = []

for i, (_, row) in enumerate(X_test.iterrows()):
    pred = int(y_pred[i])
    sev  = get_severity(row["pm25"], row["visibility"])
    resources = get_edge_resources(sev)

    # Count actions
    if pred == 1:
        if sev == "CRITICAL": agent_closes  += 1
        else:                 agent_reduces += 1

    # Resource escalation tracking
    if resources["bandwidth_limit"] > 50:
        bw_escalations += 1
        if sev in ["HIGH", "CRITICAL"]:
            correct_escalations += 1
    elif resources["bandwidth_limit"] < 50:
        bw_reductions += 1
        total_bw_saved += (50 - resources["bandwidth_limit"])

    if resources["compute_priority"] in ["MEDIUM", "HIGH"]:
        compute_escalations += 1

    # Fog hotspot simulation
    district_buf.append(sev)
    if len(district_buf) == 3:
        danger = sum(1 for s in district_buf if s in ["HIGH", "CRITICAL"])
        if danger >= 2:
            hotspot_sim += 1
        district_buf = []

    # Learning simulation
    memory.append(row["pm25"])
    if prev_pm25 > 0:
        improved = row["pm25"] < prev_pm25
        decision_str = "Reduce traffic" if pred == 1 else "Normal traffic"
        action_outcomes.append({"decision": decision_str, "improved": improved})

        recent = list(action_outcomes)[-5:]
        reduce_ineffective = sum(
            1 for o in recent
            if o["decision"] == "Reduce traffic" and not o["improved"]
        )
        if reduce_ineffective >= 3:
            old_thresh = base_threshold
            base_threshold = max(50.0, base_threshold - 5.0)
            if base_threshold != old_thresh:
                learning_triggers += 1

    prev_pm25 = row["pm25"]

dangerous_count = int(y_test.sum())
b_detected      = int(base_tp)
a_detected      = int(tp)
escalation_acc  = correct_escalations / bw_escalations * 100 if bw_escalations > 0 else 0

# ── Results ───────────────────────────────────────────────────
print("\n")
print("=" * 65)
print("  RESULTS — BASELINE vs AGENTIC SYSTEM")
print("  (tested on 20% held-out data — never seen during training)")
print("=" * 65)
print(f"  {'Metric':<40} {'Baseline':>8} {'Agentic':>8}")
print("-" * 65)
print(f"  {'Accuracy (%)':<40} {base_acc*100:>7.1f}% {test_acc*100:>7.1f}%")
print(f"  {'Precision (%)':<40} {base_precision*100:>7.1f}% {precision*100:>7.1f}%")
print(f"  {'Recall (%)':<40} {base_recall*100:>7.1f}% {recall*100:>7.1f}%")
print(f"  {'F1 Score (%)':<40} {base_f1*100:>7.1f}% {f1*100:>7.1f}%")
print(f"  {'Dangerous situations detected':<40} {b_detected:>8} {a_detected:>8}")
print(f"  {'Situations missed':<40} {dangerous_count-b_detected:>8} {dangerous_count-a_detected:>8}")
print(f"  {'Reduce traffic decisions':<40} {'N/A':>8} {agent_reduces:>8}")
print(f"  {'Road closure decisions':<40} {'0':>8} {agent_closes:>8}")
print(f"  {'Hotspot detections (fog sim)':<40} {'0':>8} {hotspot_sim:>8}")
print("-" * 65)
print("  RESOURCE ASSIGNMENT METRICS (NEW):")
print(f"  {'BW escalations (crisis zones)':<40} {'0':>8} {bw_escalations:>8}")
print(f"  {'BW reductions (safe zones)':<40} {'0':>8} {bw_reductions:>8}")
print(f"  {'Compute escalations':<40} {'0':>8} {compute_escalations:>8}")
print(f"  {'Escalation accuracy (%)':<40} {'0':>8} {escalation_acc:>7.1f}%")
print(f"  {'Total BW units saved (safe zones)':<40} {'0':>8} {total_bw_saved:>8}")
print(f"  {'Learning threshold triggers':<40} {'0':>8} {learning_triggers:>8}")
print("-" * 65)

# ── Severity breakdown ────────────────────────────────────────
print("\n  SEVERITY BREAKDOWN on test set (agentic):")
print(f"  {'Severity':<12} {'Count':>8} {'%':>8}")
print("  " + "-" * 30)
for sev in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
    count = sum(
        1 for _, r in X_test.iterrows()
        if get_severity(r["pm25"], r["visibility"]) == sev
    )
    print(f"  {sev:<12} {count:>8} {count/len(X_test)*100:>7.1f}%")

# ── Full classification report ────────────────────────────────
print("\n  FULL CLASSIFICATION REPORT:")
report = classification_report(
    y_test,
    y_pred,
    target_names=["Normal", "Dangerous"],
    output_dict=True
)

pd.DataFrame(report).transpose().to_csv(
    "classification_report.csv"
)

print("\nClassification report saved to classification_report.csv")

# ── Conclusion ────────────────────────────────────────────────
improvement = test_acc * 100 - base_acc * 100
print("=" * 65)
print("  CONCLUSION")
print("=" * 65)
print(f"  Train/test split          : 80% train / 20% test (stratified)")
print(f"  Model trained on          : {len(X_train)} rows")
print(f"  Model tested on           : {len(X_test)} UNSEEN rows")
print(f"  Accuracy improvement      : +{improvement:.1f}% over baseline")
print(f"  Hotspot detections        : {hotspot_sim} (baseline = 0)")
print(f"  Road closures issued      : {agent_closes} (baseline = 0)")
print(f"  BW escalations (correct)  : {correct_escalations}/{bw_escalations} "
      f"({escalation_acc:.1f}% accuracy)")
print(f"  BW units saved            : {total_bw_saved} (safe-zone yield)")
print(f"  Learning triggers         : {learning_triggers}")
print("=" * 65)

# ── Save results ──────────────────────────────────────────────
summary = pd.DataFrame([
    {"metric": "Train set size",              "baseline": len(X_train),              "agentic": len(X_train)},
    {"metric": "Test set size",               "baseline": len(X_test),               "agentic": len(X_test)},
    {"metric": "Accuracy %",                  "baseline": round(base_acc*100,2),     "agentic": round(test_acc*100,2)},
    {"metric": "Precision %",                 "baseline": round(base_precision*100,2),"agentic": round(precision*100,2)},
    {"metric": "Recall %",                    "baseline": round(base_recall*100,2),  "agentic": round(recall*100,2)},
    {"metric": "F1 Score %",                  "baseline": round(base_f1*100,2),      "agentic": round(f1*100,2)},
    {"metric": "ROC-AUC %",                   "baseline": 0,                         "agentic": round(auc * 100, 2)
    },
    {"metric": "Dangerous detected",          "baseline": b_detected,                "agentic": a_detected},
    {"metric": "Situations missed",           "baseline": dangerous_count-b_detected,"agentic": dangerous_count-a_detected},
    {"metric": "Road closures",               "baseline": 0,                         "agentic": agent_closes},
    {"metric": "Hotspot detections",          "baseline": 0,                         "agentic": hotspot_sim},
    {"metric": "BW escalations",              "baseline": 0,                         "agentic": bw_escalations},
    {"metric": "BW reductions",               "baseline": 0,                         "agentic": bw_reductions},
    {"metric": "Compute escalations",         "baseline": 0,                         "agentic": compute_escalations},
    {"metric": "Escalation accuracy %",       "baseline": 0,                         "agentic": round(escalation_acc,2)},
    {"metric": "BW units saved",              "baseline": 0,                         "agentic": total_bw_saved},
    {"metric": "Learning threshold triggers", "baseline": 0,                         "agentic": learning_triggers},
])
summary.to_csv("evaluation_results.csv", index=False)
print(f"\n  Results saved to: evaluation_results.csv")
print(f"  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")