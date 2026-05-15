import json
import os

from ChatAgent.chat_agent import ChatAgent
from ToolCalling.tool_calling import ToolCalling
from Agents.EHR_Agent.ehr_agent_config import EHR_AGENT_CONFIG

import logging

logger = logging.getLogger(__name__)

# ── Load prompt ──────────────────────────────────────────────────────────────
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.json")

with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    EHR_PROMPT = json.load(f)


# ── Factory ──────────────────────────────────────────────────────────────────
def create_ehr_agent() -> ChatAgent:
    agent = ChatAgent(
        api_key=EHR_AGENT_CONFIG["api_key"],
        structured_system_message=EHR_PROMPT,
        max_tokens=EHR_AGENT_CONFIG["max_tokens"],
        max_tool_use=EHR_AGENT_CONFIG["max_tool_use"],
        default_model_name=EHR_AGENT_CONFIG["default_model_name"],
        json_mode=EHR_AGENT_CONFIG["json_mode"],
        temperature=EHR_AGENT_CONFIG["temperature"],
    )

    # Register search tool
    tool_calling = ToolCalling(chat_agent=agent)
    tool_calling.register_on_agent("SEARCH_PATIENT_DATA")

    return agent


# ── Node ─────────────────────────────────────────────────────────────────────
def ehr_node(state: dict) -> dict:
    alert = state.get("alert", {})
    triage_output = state.get("triage_output", {})

    patient_id = alert.get("patient_id")
    ehr_queries = triage_output.get("ehr_queries", [])  # ← list now
    clinical_question = triage_output.get("clinical_question", "")

    if not patient_id:
        logger.error("ehr_node: no patient_id found in alert")
        return {
            **state,
            "errors": state.get("errors", []) + ["ehr_node: missing patient_id"],
        }

    if not ehr_queries:
        logger.warning("ehr_node: no ehr_queries found in triage_output")
        ehr_queries = ["general medical history and medications"]

    try:
        agent = create_ehr_agent()
        all_ehr_findings = []

        for query in ehr_queries:
            message = (
                f"Patient ID: {patient_id}\n"
                f"Clinical question: {clinical_question}\n"
                f"Search query: {query}\n\n"
                f"Use the search_patient_data tool with data_type='ehr' "
                f"to search the patient EHR and return your structured findings."
            )

            logger.info(f"ehr_node: patient={patient_id} query='{query[:50]}'")
            raw = agent.ask(message)
            result = json.loads(raw)
            all_ehr_findings.append(result)

        logger.info(f"ehr_node: completed {len(all_ehr_findings)} queries")

        return {
            **state,
            "ehr_findings": all_ehr_findings,
            "audit_log": state.get("audit_log", []) + [{
                "node": "ehr",
                "patient_id": patient_id,
                "queries": ehr_queries,
                "clinical_question": clinical_question,
                "ehr_findings": all_ehr_findings,
            }],
        }

    except json.JSONDecodeError as e:
        logger.error(f"ehr_node: JSON parse failed: {e}")
        return {
            **state,
            "ehr_findings": [{"error": str(e), "missing_data": ["EHR agent JSON parse failed"]}],
            "errors": state.get("errors", []) + [f"ehr_node JSON parse failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "ehr",
                "patient_id": patient_id,
                "queries": ehr_queries,
                "error": f"JSON parse failed: {e}",
            }],
        }

    except Exception as e:
        logger.error(f"ehr_node: failed: {e}")
        return {
            **state,
            "ehr_findings": [{"error": str(e), "missing_data": ["EHR agent failed"]}],
            "errors": state.get("errors", []) + [f"ehr_node failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "ehr",
                "patient_id": patient_id,
                "queries": ehr_queries,
                "error": str(e),
            }],
        }
