import logging

logger = logging.getLogger(__name__)


def route_after_safety_check(state: dict) -> str:
    if state.get("escalate"):
        logger.warning("router: safety_check (escalation) → emergency_report")
        return "emergency_report"
    logger.info("router: safety_check → triage")
    return "triage"


def route_after_triage(state: dict) -> str:
    severity = state.get("severity_class", "UNKNOWN")
    if severity in ["CRITICAL", "HIGH"]:
        logger.warning(f"router: triage (severity={severity}) → emergency_report")
        return "emergency_report"
    logger.info(f"router: triage (severity={severity}) → parallel_retrieval")
    return "parallel_retrieval"
