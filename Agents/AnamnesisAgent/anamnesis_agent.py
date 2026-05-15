import json
import os

from ChatAgent.chat_agent import ChatAgent
from ToolCalling.tool_calling import ToolCalling
from Agents.AnamnesisAgent.anamnesis_agent_config import ANAMNESIS_AGENT_CONFIG

import logging

logger = logging.getLogger(__name__)

# ── Load prompt ──────────────────────────────────────────────────────────────
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.json")

with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    ANAMNESIS_PROMPT = json.load(f)


# ── Factory ──────────────────────────────────────────────────────────────────
def create_anamnesis_agent() -> ChatAgent:
    agent = ChatAgent(
        api_key=ANAMNESIS_AGENT_CONFIG["api_key"],
        structured_system_message=ANAMNESIS_PROMPT,
        max_tokens=ANAMNESIS_AGENT_CONFIG["max_tokens"],
        max_tool_use=ANAMNESIS_AGENT_CONFIG["max_tool_use"],
        default_model_name=ANAMNESIS_AGENT_CONFIG["default_model_name"],
        json_mode=ANAMNESIS_AGENT_CONFIG["json_mode"],
        temperature=ANAMNESIS_AGENT_CONFIG["temperature"],
    )

    # Register search tool
    tool_calling = ToolCalling(chat_agent=agent)
    tool_calling.register_on_agent("SEARCH_PATIENT_DATA")

    return agent


# ── Node ─────────────────────────────────────────────────────────────────────
def anamnesis_node(state: dict) -> dict:
    alert = state.get("alert", {})
    triage_output = state.get("triage_output", {})

    patient_id = alert.get("patient_id")
    anamnesis_queries = triage_output.get("anamnesis_queries", [])
    clinical_question = triage_output.get("clinical_question", "")

    if not patient_id:
        logger.error("anamnesis_node: no patient_id found in alert")
        return {
            **state,
            "errors": state.get("errors", []) + ["anamnesis_node: missing patient_id"],
        }

    if not anamnesis_queries:
        logger.warning("anamnesis_node: no anamnesis_queries found in triage_output")
        anamnesis_queries = ["recent symptoms and medication adherence"]

    try:
        agent = create_anamnesis_agent()
        all_anamnesis_findings = []

        for query in anamnesis_queries:
            message = (
                f"Patient ID: {patient_id}\n"
                f"Clinical question: {clinical_question}\n"
                f"Search query: {query}\n\n"
                f"Use the search_patient_data tool with data_type='anamnesis' "
                f"to search the patient self-reported history and return your structured findings."
            )

            logger.info(f"anamnesis_node: patient={patient_id} query='{query[:50]}'")
            raw = agent.ask(message)
            result = json.loads(raw)
            all_anamnesis_findings.append(result)

        logger.info(f"anamnesis_node: completed {len(all_anamnesis_findings)} queries")

        return {
            **state,
            "anamnesis_findings": all_anamnesis_findings,
            "audit_log": state.get("audit_log", []) + [{
                "node": "anamnesis",
                "patient_id": patient_id,
                "queries": anamnesis_queries,
                "clinical_question": clinical_question,
                "anamnesis_findings": all_anamnesis_findings,
            }],
        }

    except json.JSONDecodeError as e:
        logger.error(f"anamnesis_node: JSON parse failed: {e}")
        return {
            **state,
            "anamnesis_findings": [{"error": str(e), "missing_data": ["Anamnesis agent JSON parse failed"]}],
            "errors": state.get("errors", []) + [f"anamnesis_node JSON parse failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "anamnesis",
                "patient_id": patient_id,
                "queries": anamnesis_queries,
                "error": f"JSON parse failed: {e}",
            }],
        }

    except Exception as e:
        logger.error(f"anamnesis_node: failed: {e}")
        return {
            **state,
            "anamnesis_findings": [{"error": str(e), "missing_data": ["Anamnesis agent failed"]}],
            "errors": state.get("errors", []) + [f"anamnesis_node failed: {e}"],
            "audit_log": state.get("audit_log", []) + [{
                "node": "anamnesis",
                "patient_id": patient_id,
                "queries": anamnesis_queries,
                "error": str(e),
            }],
        }
