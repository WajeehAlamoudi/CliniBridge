import json
import os

from ChatAgent.chat_agent import ChatAgent
from Agents.TriageAgent.triage_agent_config import TRIAGE_AGENT_CONFIG


import logging
logger = logging.getLogger(__name__)


# ── Load prompt ──────────────────────────────────────────────────────────────
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.json")

with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    TRIAGE_PROMPT = json.load(f)


# ── Factory ──────────────────────────────────────────────────────────────────
def create_triage_agent() -> ChatAgent:
    return ChatAgent(
        api_key=TRIAGE_AGENT_CONFIG["api_key"],
        structured_system_message=TRIAGE_PROMPT,
        max_tokens=TRIAGE_AGENT_CONFIG["max_tokens"],
        max_tool_use=TRIAGE_AGENT_CONFIG["max_tool_use"],
        default_model_name=TRIAGE_AGENT_CONFIG["default_model_name"],
        json_mode=TRIAGE_AGENT_CONFIG["json_mode"],
        temperature=TRIAGE_AGENT_CONFIG["temperature"],
    )


# ── Node ─────────────────────────────────────────────────────────────────────
def triage_node(state: dict) -> dict:
    alert = state.get("alert", {})

    if not alert:
        logger.error("triage_node: empty alert in state")
        return {
            **state,
            "errors": state.get("errors", []) + ["triage_node: empty alert"],
        }

    try:
        agent = create_triage_agent()
        message = (
            f"Analyze this alert and return your triage decision:\n"
            f"{json.dumps(alert, indent=2)}"
        )

        logger.info(f"triage_node: patient={alert.get('patient_id')}")
        raw = agent.ask(message)
        result = json.loads(raw)

        severity_class = result.get("severity", {}).get("class", "UNKNOWN")
        logger.info(f"triage_node: severity={severity_class}")

        return {
            **state,
            "triage_output":  result,
            "severity_class": severity_class,
            "audit_log": state.get("audit_log", []) + [{
                "node": "triage",
                "patient_id": alert.get("patient_id"),
                "severity_class": severity_class,
                "triage_output": result,
            }],
        }

    except json.JSONDecodeError as e:
        logger.error(f"triage_node: JSON parse failed: {e}")
        return {
            **state,
            "errors": state.get("errors", []) + [f"triage_node JSON parse failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "triage",
                "patient_id": alert.get("patient_id"),
                "error": f"JSON parse failed: {e}",
            }],
        }

    except Exception as e:
        logger.error(f"triage_node: failed: {e}")
        return {
            **state,
            "errors": state.get("errors", []) + [f"triage_node failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "triage",
                "patient_id": alert.get("patient_id"),
                "error": f"JSON parse failed: {e}",
            }],
        }
