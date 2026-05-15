import json
import os

from ChatAgent.chat_agent import ChatAgent
from Agents.SynthesisAgent.synthesis_agent_config import SYNTHESIS_AGENT_CONFIG

import logging

logger = logging.getLogger(__name__)

# ── Load prompt ──────────────────────────────────────────────────────────────
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.json")

with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    SYNTHESIS_PROMPT = json.load(f)


# ── Factory ──────────────────────────────────────────────────────────────────
def create_synthesis_agent() -> ChatAgent:
    return ChatAgent(
        api_key=SYNTHESIS_AGENT_CONFIG["api_key"],
        structured_system_message=SYNTHESIS_PROMPT,
        max_tokens=SYNTHESIS_AGENT_CONFIG["max_tokens"],
        max_tool_use=SYNTHESIS_AGENT_CONFIG["max_tool_use"],
        default_model_name=SYNTHESIS_AGENT_CONFIG["default_model_name"],
        json_mode=SYNTHESIS_AGENT_CONFIG["json_mode"],
        temperature=SYNTHESIS_AGENT_CONFIG["temperature"],
    )


# ── Node ─────────────────────────────────────────────────────────────────────
def synthesis_node(state: dict) -> dict:
    alert = state.get("alert", {})
    triage_output = state.get("triage_output", {})
    ehr_findings = state.get("ehr_findings", [])
    anamnesis_findings = state.get("anamnesis_findings", [])

    if not alert:
        logger.error("synthesis_node: empty alert in state")
        return {
            **state,
            "errors": state.get("errors", []) + ["synthesis_node: empty alert"],
        }

    try:
        agent = create_synthesis_agent()

        message = (
            f"Synthesize the following into a Clinical Context Brief.\n\n"
            f"ORIGINAL ALERT:\n{json.dumps(alert, indent=2)}\n\n"
            f"TRIAGE DECISION:\n{json.dumps(triage_output, indent=2)}\n\n"
            f"EHR FINDINGS ({len(ehr_findings)} queries):\n{json.dumps(ehr_findings, indent=2)}\n\n" 
            f"ANAMNESIS FINDINGS ({len(anamnesis_findings)} queries):\n{json.dumps(anamnesis_findings, indent=2)}"

        )

        logger.info(f"synthesis_node: patient={alert.get('patient_id')}")
        raw = agent.ask(message)
        result = json.loads(raw)

        logger.info("synthesis_node: brief generated successfully")

        return {
            **state,
            "clinical_brief": result,
            "audit_log": state.get("audit_log", []) + [{
                "node": "synthesis",
                "patient_id": alert.get("patient_id"),
                "clinical_brief": result,
            }],
        }

    except json.JSONDecodeError as e:
        logger.error(f"synthesis_node: JSON parse failed: {e}")
        return {
            **state,
            "errors": state.get("errors", []) + [f"synthesis_node JSON parse failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "synthesis",
                "patient_id": alert.get("patient_id"),
                "error": f"JSON parse failed: {e}",
            }],
        }

    except Exception as e:
        logger.error(f"synthesis_node: failed: {e}")
        return {
            **state,
            "errors": state.get("errors", []) + [f"synthesis_node failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "synthesis",
                "patient_id": alert.get("patient_id"),
                "error": str(e),
            }],
        }
