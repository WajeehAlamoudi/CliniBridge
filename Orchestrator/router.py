import logging

logger = logging.getLogger(__name__)


def route_after_safety_check(state: dict) -> str:
    if state.get("escalate"):
        logger.warning("router: escalation → emergency_report")
        return "emergency_report"
    logger.info("router: safe → triage")
    return "triage"


def route_after_triage(state: dict) -> str:
    severity = state.get("severity_class", "UNKNOWN")
    if severity in ["CRITICAL", "HIGH"]:
        logger.warning(f"router: severity={severity} → emergency_report")
        return "emergency_report"
    logger.info(f"router: severity={severity} → parallel_retrieval")
    return "parallel_retrieval"
