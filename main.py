from dotenv import load_dotenv
load_dotenv()

import json
import logging
import os
from Orchestrator.orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load alert
with open(os.path.join(BASE_DIR, "data", "alerts", "scenario_4.json"), "r") as f:
    alert = json.load(f)

# Run
orchestrator = Orchestrator()
brief = orchestrator.run(alert)

# Print
print(json.dumps(brief, indent=2, ensure_ascii=False))
