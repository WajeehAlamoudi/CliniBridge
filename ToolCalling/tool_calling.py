from typing import Optional, Union, List, Callable, Any
import os
from ChatAgent.chat_agent import ChatAgent
from Embedder.embedder import Embedder
from ToolCalling.tool_calling_utils import serialize_result
from ToolCalling.tool_calling_config import TOOL_CALLING_CONFIG

import logging
logger = logging.getLogger(__name__)


class ToolCalling:
    def __init__(
            self,
            chat_agent: Optional[ChatAgent] = None,
            embedder:   Optional[Embedder] = None,
    ):
        self.chat_agent = chat_agent
        self.embedder = embedder

        # Load search config
        self.search_config = TOOL_CALLING_CONFIG["search_patient_data"]

    def search_patient_data(
            self,
            patient_id: str,
            data_type: str,
            query: str,
            top_k: int = None,
    ) -> dict:

        try:
            # ── Get config values ────────────────────────────────────────
            if top_k is None:
                top_k = self.search_config.get(data_type, {}).get("top_k", 5)

            # ── Build path FROM CONFIG ────────────────────────────────────
            base_path = self.search_config.get("base_path", "data/patients")
            file_path = os.path.join(base_path, patient_id, "information", f"{data_type}.json")

            # ── Load index from disk ─────────────────────────────────────
            index, chunk_map = Embedder._load_from_disk(file_path)

            if index is None or not chunk_map:
                return {
                    "success": False,
                    "error": f"No index found for {patient_id}/{data_type}. Run embedding first.",
                }

            # ── Search ───────────────────────────────────────────────────
            results = Embedder.search(
                index=index,
                chunk_map=chunk_map,
                query=query,
                top_k=top_k,
            )

            logger.info(
                f"search_patient_data: patient={patient_id} "
                f"type={data_type} top_k={top_k} hits={len(results)}"
            )

            return {
                "success": True,
                "patient_id": patient_id,
                "data_type": data_type,
                "query": query,
                "results": serialize_result(results),
            }

        except Exception as e:
            logger.error(f"search_patient_data failed: {e}")
            return {"success": False, "error": str(e)}

    def get_functions(self) -> List[Callable]:
        return [self.search_patient_data]

    def register_on_agent(
            self,
            function_name: str,
            chat_agent: Optional[Any] = None,
    ) -> None:

        if function_name.upper() == "SEARCH_PATIENT_DATA":
            target_agent = chat_agent if chat_agent is not None else self.chat_agent

            if target_agent is None:
                raise ValueError("No chat_agent provided")

            target_agent.register_function(
                func=self.search_patient_data,
                description=(
                    "Search patient medical data using semantic similarity. "
                    "Use data_type='ehr' for medical history, medications, labs, visit notes. "
                    "Use data_type='anamnesis' for patient self-reported symptoms and adherence."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "patient_id": {
                            "type": "string",
                            "description": "Patient ID. e.g. P001"
                        },
                        "data_type": {
                            "type": "string",
                            "enum": ["ehr", "anamnesis"],
                            "description": "Which data source to search. ehr or anamnesis"
                        },
                        "query": {
                            "type": "string",
                            "description": "What to search for"
                        },
                    },
                    "required": ["patient_id", "data_type", "query"]
                }
            )

            logger.info("Registered tool: search_patient_data")
            return

        raise ValueError(f"Unknown function: {function_name}")
