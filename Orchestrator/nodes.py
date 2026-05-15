import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from Orchestrator.state import ClinicalState
from Agents.EHR_Agent.ehr_agent import ehr_node
from Agents.AnamnesisAgent.anamnesis_agent import anamnesis_node

logger = logging.getLogger(__name__)


def emergency_report_node(state: ClinicalState) -> ClinicalState:
    alert = state.get("alert", {})
    triage_output = state.get("triage_output", {})

    logger.warning(f"emergency_report_node: patient={alert.get('patient_id')}")

    brief = {
        "status": "EMERGENCY ESCALATION",
        "message": "Alert requires immediate human attention. Full AI synthesis skipped.",
        "action": "Contact clinician and patient NOW. Do not wait.",
        "patient_id": alert.get("patient_id"),
        "alert": alert,
        "triage_output": triage_output if triage_output else "Triage not completed — safety check triggered escalation",
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": "emergency_report_node — no LLM involved",
    }

    return {
        **state,
        "clinical_brief": brief,
        "audit_log": state.get("audit_log", []) + [{"node": "emergency_report", "output": brief}],
    }


def parallel_retrieval_node(state: ClinicalState) -> ClinicalState:
    errors = list(state.get("errors", []))
    ehr_result = None
    anamnesis_result = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_ehr = executor.submit(ehr_node, state)
        future_anamnesis = executor.submit(anamnesis_node, state)

        for future in as_completed([future_ehr, future_anamnesis]):
            try:
                result = future.result()
                if future == future_ehr:
                    ehr_result = result
                else:
                    anamnesis_result = result
            except Exception as e:
                errors.append(str(e))

    ehr_findings = (
        ehr_result.get("ehr_findings", [{"error": "EHR failed"}])
        if ehr_result else [{"error": "EHR failed"}]
    )

    anamnesis_findings = (
        anamnesis_result.get("anamnesis_findings", [{"error": "Anamnesis failed"}])
        if anamnesis_result else [{"error": "Anamnesis failed"}]
    )

    return {
        **state,
        "ehr_findings": ehr_findings,
        "anamnesis_findings": anamnesis_findings,
        "errors": errors,
        "audit_log": state.get("audit_log", []) + [{
            "node": "parallel_retrieval",
            "patient_id": state.get("alert", {}).get("patient_id"),
            "ehr_queries": state.get("triage_output", {}).get("ehr_queries", []),
            "anamnesis_queries": state.get("triage_output", {}).get("anamnesis_queries", []),
            "ehr_findings": ehr_findings,
            "anamnesis_findings": anamnesis_findings,
            "errors": errors,
        }],
    }
