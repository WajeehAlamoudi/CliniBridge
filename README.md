# CliniBridge

CliniBridge is an AI-powered multi-agent clinical alert orchestration system. It takes a simulated Remote Patient Monitoring (RPM) alert, retrieves relevant Electronic Health Record (EHR) and anamnesis context, and produces a structured Clinical Context Brief for clinician review.

The project is built as an educational prototype using simulated patient data. It focuses on combining disconnected clinical information into a single readable summary.

## What The Project Does

CliniBridge processes a clinical alert through a multi-agent workflow:

1. A safety check reviews the alert against hardcoded escalation thresholds.
2. A triage agent classifies urgency and generates retrieval queries.
3. An EHR agent retrieves relevant medical history and structured facts.
4. An anamnesis agent retrieves relevant self-reported patient context.
5. A synthesis agent combines all outputs into a final Clinical Context Brief.
6. The system stores the result as:
   - a JSON audit log
   - a PDF clinical brief

## Workflow Graph

The graph below shows the overall workflow used by the orchestrator.

![ClinicalBridge Graph](graph.png)

## Main Components

- `Orchestrator`
  - Coordinates the workflow
  - Handles routing between nodes
  - Saves audit logs and PDFs

- `Safety Check`
  - Decides whether the alert should escalate immediately

- `Triage Agent`
  - Classifies alert severity
  - Formulates EHR and anamnesis search queries

- `EHR Agent`
  - Retrieves clinically relevant information from the patient EHR

- `Anamnesis Agent`
  - Retrieves self-reported patient context such as symptoms, adherence, and lifestyle

- `Synthesis Agent`
  - Produces the final Clinical Context Brief

## Project Structure

```text
CliniBridge/
|-- main.py
|-- graph.png
|-- README.md
|-- requirements.txt
|-- .env.example
|-- Agents/
|-- ChatAgent/
|-- Embedder/
|-- Orchestrator/
|-- ToolCalling/
`-- data/
    |-- alerts/
    `-- patients/
```

## Data Layout

Each patient is stored under:

```text
data/patients/<PATIENT_ID>/
```

A patient folder may contain:

- `information/`
  - `ehr.json`
  - `anamnesis.json`

- `embeddings/`
  - Saved FAISS indexes and maps

- `logs/`
  - Generated JSON audit logs
  - Generated PDF clinical briefs

Example:

```text
data/patients/P001/logs/
data/patients/P002/logs/
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies from `requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Fill in your `OPENROUTER_API_KEY`.

Example:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## How To Run

The project runs from `main.py`.

By default, `main.py` loads `scenario_1.json`.

Run it with:

```powershell
python main.py
```

## How To Change The Scenario

Open `main.py` and change the scenario file name in this section:

```python
with open(os.path.join(BASE_DIR, "data", "alerts", "scenario_1.json"), "r") as f:
    alert = json.load(f)
```

For example, to run another scenario:

```python
with open(os.path.join(BASE_DIR, "data", "alerts", "scenario_2.json"), "r") as f:
    alert = json.load(f)
```

Then run:

```powershell
python main.py
```

## Output

For each run, CliniBridge produces:

- Terminal output with the final structured result
- A JSON audit log
- A PDF clinical brief

These files are stored in the matching patient folder under:

```text
data/patients/<PATIENT_ID>/logs/
```

Example:

```text
data/patients/P001/logs/P001_YYYYMMDD_HHMMSS.json
data/patients/P001/logs/P001_YYYYMMDD_HHMMSS.pdf
```

If a patient ID is missing, the system uses:

```text
data/patients/unknown/logs/
```

## Clinical Brief Output

The final Clinical Context Brief is synthesized from:

- The original RPM alert
- The triage output
- EHR findings
- Anamnesis findings

The brief is intended to summarize:

- What triggered the alert
- The patient's relevant context
- Possible risks
- Suggested next actions
- Missing information or uncertainty

