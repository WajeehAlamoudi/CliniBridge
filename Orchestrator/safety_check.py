import logging

logger = logging.getLogger(__name__)

# Hardcoded clinical thresholds for immediate escalation ───────────────────────


CRITICAL_THRESHOLDS = {
    "blood_pressure": {
        "systolic": 200,
        "diastolic": 120,
    },
    "heart_rate": {
        "min": 30,
        "max": 160,
    },
    "spo2": {
        "min": 88,
    },
    "blood_glucose": {
        "min": 50,
        "max": 400,
    },
    "weight": None,
}


# SAFETY CHECK NODE ───────────────────────────────────────────────────────────

def safety_check_node(state: dict) -> dict:
    """
    First node in the pipeline. Runs before any LLM agent.
    Reads raw alert and checks against hardcoded thresholds.

    No LLM. No API call. Instant.

    IN:
        state["alert"] → raw RPM alert JSON

    OUT:
        state["escalate"]  = True  → route to emergency report
        state["escalate"]  = False → route to triage agent
        state["audit_log"] → updated with safety check result
    """
    alert = state.get("alert", {})
    reading = alert.get("reading", "").lower().replace(" ", "_")
    value = alert.get("value", "")

    escalate = False
    reason = None

    try:

        # ── Blood Pressure ───────────────────────────────────────────────────
        if reading == "blood_pressure":
            systolic, diastolic = map(int, str(value).split("/"))
            t = CRITICAL_THRESHOLDS["blood_pressure"]

            if systolic >= t["systolic"] or diastolic >= t["diastolic"]:
                escalate = True
                reason = (
                    f"BP {value} exceeds critical threshold "
                    f"({t['systolic']}/{t['diastolic']} mmHg)"
                )

        # ── Heart Rate ───────────────────────────────────────────────────────
        elif reading == "heart_rate":
            hr = int(float(str(value)))
            t = CRITICAL_THRESHOLDS["heart_rate"]

            if hr < t["min"] or hr > t["max"]:
                escalate = True
                reason = (
                    f"Heart rate {value} bpm outside critical range "
                    f"({t['min']}-{t['max']} bpm)"
                )

        # ── SpO2 ─────────────────────────────────────────────────────────────
        elif reading == "spo2":
            spo2 = int(float(str(value)))
            t = CRITICAL_THRESHOLDS["spo2"]

            if spo2 < t["min"]:
                escalate = True
                reason = (
                    f"SpO2 {value}% below critical threshold "
                    f"({t['min']}%)"
                )

        # ── Blood Glucose ────────────────────────────────────────────────────
        elif reading == "blood_glucose":
            glucose = float(str(value))
            t = CRITICAL_THRESHOLDS["blood_glucose"]

            if glucose < t["min"] or glucose > t["max"]:
                escalate = True
                reason = (
                    f"Blood glucose {value} mg/dL outside critical range "
                    f"({t['min']}-{t['max']} mg/dL)"
                )

        # ── Unknown reading type ─────────────────────────────────────────────
        else:
            logger.warning(f"safety_check: unknown reading type '{reading}' — passing to triage")

    except Exception as e:
        # If parsing fails → do not escalate, let triage handle it
        logger.error(f"safety_check: failed to parse value '{value}' for '{reading}': {e}")
        escalate = False

    # ── Log result ───────────────────────────────────────────────────────────
    if escalate:
        logger.warning(f"safety_check: ESCALATE — {reason}")
    else:
        logger.info(f"safety_check: OK — reading='{reading}' value='{value}' passes thresholds")

    log_entry = {
        "node": "safety_check",
        "reading": reading,
        "value": value,
        "escalate": escalate,
        "reason": reason,
    }

    return {
        **state,
        "escalate": escalate,
        "audit_log": state.get("audit_log", []) + [log_entry],
    }
