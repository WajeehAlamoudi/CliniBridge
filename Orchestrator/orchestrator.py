import json
import logging
import os
from datetime import datetime

from langgraph.graph import StateGraph, END

import textwrap
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from Orchestrator.state import ClinicalState
from Orchestrator.safety_check import safety_check_node
from Orchestrator.router import route_after_safety_check, route_after_triage
from Orchestrator.nodes import emergency_report_node, parallel_retrieval_node
from Agents.TriageAgent.triage_agent import triage_node
from Agents.SynthesisAgent.synthesis_agent import synthesis_node

logger = logging.getLogger(__name__)


def build_graph():
    graph = StateGraph(ClinicalState)

    # Nodes
    graph.add_node("safety_check", safety_check_node)
    graph.add_node("triage", triage_node)
    graph.add_node("emergency_report", emergency_report_node)
    graph.add_node("parallel_retrieval", parallel_retrieval_node)
    graph.add_node("synthesis", synthesis_node)

    # Entry
    graph.set_entry_point("safety_check")

    # Conditional edges
    graph.add_conditional_edges(
        "safety_check",
        route_after_safety_check,
        {
            "emergency_report": "emergency_report",
            "triage": "triage",
        }
    )

    graph.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "emergency_report": "emergency_report",
            "parallel_retrieval": "parallel_retrieval",
        }
    )

    # Fixed edges
    graph.add_edge("parallel_retrieval", "synthesis")
    graph.add_edge("synthesis", END)
    graph.add_edge("emergency_report", END)

    app = graph.compile()

    try:
        img_bytes = app.get_graph().draw_mermaid_png()
        with open("graph.png", "wb") as f:
            f.write(img_bytes)
        print("Graph saved to graph.png")
    except Exception as e:
        print(f"Could not generate graph image: {e}")

    return app


class Orchestrator:

    def __init__(self):
        logger.info("Orchestrator: building graph")
        self.app = build_graph()
        logger.info("Orchestrator: ready")

    def run(self, alert: dict) -> dict:
        if not isinstance(alert, dict) or not alert:
            raise ValueError("alert must be a non-empty dict")

        logger.info(f"Orchestrator.run: patient={alert.get('patient_id')}")

        initial_state: ClinicalState = {
            "alert": alert,
            "triage_output": None,
            "severity_class": None,
            "ehr_findings": None,
            "anamnesis_findings": None,
            "clinical_brief": None,
            "escalate": False,
            "errors": [],
            "audit_log": [],
        }

        final_state = self.app.invoke(initial_state)
        self._save_audit_log(final_state)
        filepath = self._save_audit_log(final_state)

        if filepath and final_state.get("clinical_brief") is not None:
            self._save_audit_pdf(filepath, state=final_state)

        if final_state.get("errors"):
            logger.warning(f"Errors: {final_state['errors']}")

        return final_state

    def _save_audit_log(self, state: ClinicalState) -> str | None:
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            patient_id = state.get("alert", {}).get("patient_id", "unknown")
            logs_dir = os.path.join(base_dir, "data", "patients", patient_id, "logs")

            os.makedirs(logs_dir, exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(logs_dir, f"{patient_id}_{timestamp}.json")

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "patient_id": patient_id,
                    "timestamp": timestamp,
                    "alert": state.get("alert"),
                    "triage_output": state.get("triage_output"),
                    "severity_class": state.get("severity_class"),
                    "ehr_findings": state.get("ehr_findings"),
                    "anamnesis_findings": state.get("anamnesis_findings"),
                    "clinical_brief": state.get("clinical_brief"),
                    "escalate": state.get("escalate"),
                    "errors": state.get("errors"),
                    "audit_log": state.get("audit_log"),
                }, f, indent=2, ensure_ascii=False)

            logger.info(f"Audit log saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save audit log: {e}")

    def _save_audit_pdf(self, filepath: str, state: dict) -> None:
        pdf_path = os.path.splitext(filepath)[0] + ".pdf"
        brief = state.get("clinical_brief", {}) or {}
        patient_id = state.get("alert", {}).get("patient_id", "unknown")

        pdf = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4

        x = 50
        y = height - 50
        line_height = 14
        max_chars = 95

        def new_page():
            nonlocal y
            pdf.showPage()
            y = height - 50

        def write_line(text="", indent=0, bold=False):
            nonlocal y
            lines = textwrap.wrap(str(text), width=max_chars) or [""]

            for line in lines:
                if y < 50:
                    new_page()
                pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
                pdf.drawString(x + indent, y, line)
                y -= line_height

        def render_value(key, value, indent=0):
            if isinstance(value, dict):
                if key is not None:
                    write_line(str(key).replace("_", " ").title(), indent=indent, bold=True)
                for sub_key, sub_value in value.items():
                    render_value(sub_key, sub_value, indent=indent + 20)

            elif isinstance(value, list):
                if key is not None:
                    write_line(str(key), indent=indent, bold=True)

                for item in value:
                    if isinstance(item, (dict, list)):
                        render_value("-", item, indent=indent + 20)
                    else:
                        write_line(f"- {item}", indent=indent + 20)

            else:
                if key is None:
                    write_line(str(value), indent=indent)
                else:
                    write_line(f"{key}: {value}", indent=indent)

        pdf.setTitle("Clinical Brief")

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(x, y, "Clinical Brief")
        y -= 24

        pdf.setFont("Helvetica", 10)
        write_line(f"Patient ID: {patient_id}")
        write_line()

        if brief:
            render_value(None, brief, indent=0)
        else:
            write_line("No clinical brief available.")

        pdf.save()
        logger.info(f"Audit PDF saved: {pdf_path}")
