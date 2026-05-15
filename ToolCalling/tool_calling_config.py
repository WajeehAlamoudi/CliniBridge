import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOOL_CALLING_CONFIG = {
    "search_patient_data": {
        "base_path": os.path.join(BASE_DIR, "data", "patients"),
        "ehr": {
            "top_k": 5,
        },
        "anamnesis": {
            "top_k": 20,
        },
    }
}
