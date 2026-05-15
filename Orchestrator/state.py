from typing import TypedDict, Optional, List


class ClinicalState(TypedDict, total=False):
    """
    Shared state passed between every node in the LangGraph pipeline.
    Each node reads what it needs and writes its output back.

    Fields are filled progressively as the pipeline runs.
    Every node receives the full state and returns the full state.
    """

    # ── Input ────────────────────────────────────────────────────────────────
    alert: dict

    # ── Agent 1 output ───────────────────────────────────────────────────────
    triage_output: Optional[dict]  # full triage JSON from Agent 1
    severity_class: Optional[str]  # CRITICAL / HIGH / ELEVATED / MODERATE / LOW

    # ── Agent 2 output ───────────────────────────────────────────────────────
    ehr_findings: Optional[List[dict]]  # one dict per ehr_query

    # ── Agent 3 output ───────────────────────────────────────────────────────
    anamnesis_findings: Optional[List[dict]]  # one dict per anamnesis_query

    # ── Agent 4 output ───────────────────────────────────────────────────────
    clinical_brief: Optional[dict]  # final 6-section Clinical Context Brief

    # ── Control ──────────────────────────────────────────────────────────────
    escalate: bool  # True = skip agents, escalate immediately

    # ── Meta ─────────────────────────────────────────────────────────────────
    errors: List[str]  # any failures across all nodes
    audit_log: List[dict]  # full trace of every node input/output
