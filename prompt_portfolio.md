# CliniBridge: Prompt Engineering Portfolio

This portfolio documents the systematic design, iteration history, output schemas, and failure mode analyses for each of the four specialized agents in the **ClinicalBridge** (CliniBridge) system:
1.  **Alert Triage Agent**
2.  **EHR Retrieval Agent**
3.  **Anamnesis Agent**
4.  **Synthesis Agent**

Each agent's prompt was developed through three key versions to enforce schema safety, prevent hallucinations, translate colloquialisms, and guarantee critical clinical boundaries.

---

## 1. Alert Triage Agent

### 1.1 Role and Task Definition
The Alert Triage Agent processes raw Remote Patient Monitoring (RPM) telemetry. Its task is to extract the patient ID, classify urgency, format a summarizing clinical question, and generate separate array queries for Electronic Health Record (EHR) history search and Anamnesis (patient self-reported) search.

### 1.2 Prompt Iteration History
*   **Version 1 (Initial Prototype)**: A direct zero-shot prompt.
    ```text
    You are a triage assistant. Look at this patient alert and tell me if it is critical or not. Also suggest what we should look for in their records.
    ```
    *   *Failure Mode*: High severity volatility. Output was unstructured raw text, making downstream parsing impossible. Frequently missed patient identifiers.
*   **Version 2 (Structured Input/Output)**: System prompt mapping out five severity levels and enforcing JSON output.
    ```text
    Classify the alert as CRITICAL, HIGH, ELEVATED, MODERATE, or LOW. Return a JSON containing:
    {
      "severity": "class",
      "reason": "text",
      "patient_id": "id",
      "queries": ["list"]
    }
    ```
    *   *Failure Mode*: Combined queries into a single list rather than separate EHR and Anamnesis arrays. Did not provide specific guidelines on what telemetry values map to which severity classes.
*   **Version 3 (Production - Current)**: Complete clinical triage guidelines, split search scopes (`ehr_queries` vs `anamnesis_queries`), few-shot formatting, and safety rules preventing diagnostic claims.
    *   *Current implementation details*: Located in [prompt.json](file:///d:/Workspace/Projects/PromptProject/CliniBridge/Agents/TriageAgent/prompt.json).

### 1.3 Production System Prompt
```json
{
  "ROLE": "You are a clinical triage specialist in a remote patient monitoring system. Your only job is to receive RPM (Remote Patient Monitoring) alerts and classify their urgency. You do NOT diagnose. You do NOT treat. You classify and formulate search queries for downstream agents.",
  "SEVERITY_CLASSES": {
    "CRITICAL": { "score_range": "9-10", "definition": "Immediate life threat. Requires urgent human attention without delay." },
    "HIGH": { "score_range": "7-8", "definition": "Urgent. Requires clinician attention within 1-2 hours." },
    "ELEVATED": { "score_range": "5-6", "definition": "Above normal. Requires attention within the same day." },
    "MODERATE": { "score_range": "3-4", "definition": "Mildly abnormal. Monitor and follow up within 24-48 hours." },
    "LOW": { "score_range": "1-2", "definition": "Within acceptable variance. Log and monitor." }
  },
  "TASK": "Given an RPM alert JSON, you must analyze it and return a structured triage decision. You must consider the alert values, thresholds, device type, and any trend data if provided."
}
```

### 1.4 Output Schema
```json
{
  "type": "object",
  "properties": {
    "severity": {
      "type": "object",
      "properties": {
        "score": { "type": "integer", "minimum": 1, "maximum": 10 },
        "class": { "type": "string", "enum": ["CRITICAL", "HIGH", "ELEVATED", "MODERATE", "LOW"] },
        "reason": { "type": "string" }
      },
      "required": ["score", "class", "reason"]
    },
    "patient_info": {
      "type": "object",
      "properties": {
        "patient_id": { "type": "string" },
        "reading_type": { "type": "string" },
        "reading_value": { "type": "string" },
        "threshold": { "type": "string" },
        "deviation": { "type": "string" }
      },
      "required": ["patient_id", "reading_type", "reading_value"]
    },
    "ehr_queries": { "type": "array", "items": { "type": "string" } },
    "anamnesis_queries": { "type": "array", "items": { "type": "string" } },
    "clinical_question": { "type": "string" }
  },
  "required": ["severity", "patient_info", "ehr_queries", "anamnesis_queries", "clinical_question"]
}
```

### 1.5 Few-Shot Example
*Input*:
```json
{
  "patient_id": "P001",
  "reading": "blood_pressure",
  "value": "178/108",
  "unit": "mmHg",
  "threshold": "140/90",
  "alert_level": "HIGH"
}
```
*Output*:
```json
{
  "severity": {
    "score": 7,
    "class": "HIGH",
    "reason": "BP 178/108 is significantly above threshold of 140/90. Systolic 38 points above threshold indicates urgent hypertensive episode requiring prompt clinical review."
  },
  "patient_info": {
    "patient_id": "P001",
    "reading_type": "blood_pressure",
    "reading_value": "178/108",
    "threshold": "140/90",
    "deviation": "systolic +38 mmHg, diastolic +18 mmHg above threshold"
  },
  "ehr_queries": [
    "hypertension history and diagnosis date",
    "antihypertensive medications and doses",
    "recent blood pressure labs and trends"
  ],
  "anamnesis_queries": [
    "medication adherence and missed doses",
    "recent symptoms headache and dizziness",
    "lifestyle changes diet and salt intake"
  ],
  "clinical_question": "Why is this hypertensive patient experiencing a significant BP elevation and what is the most likely cause?"
}
```

### 1.6 Failure Mode Analysis
*   *Observed Failure*: The agent classified a diabetic glucose level of `210 mg/dL` as `HIGH` severity. Although glucose was above `180`, it was not critical without symptoms.
*   *Mitigation*: Integrated explicit limits in the system prompt guidelines (`MODERATE` for glucose `180-249`, `HIGH` for `300-400`). Added negative rules preventing immediate escalation of moderately elevated readings if patient-reported context is benign.

---

## 2. EHR Retrieval Agent

### 2.1 Role and Task Definition
The EHR Retrieval Agent operates as a clinical data analyst. It uses the `SEARCH_PATIENT_DATA` tool to fetch longitudinal history from vector stores, filtering for active diagnoses, active treatments, and lab baselines. It is explicitly prohibited from diagnosing.

### 2.2 Prompt Iteration History
*   **Version 1**: Simple instructions to fetch and clean data.
    ```text
    Find all medical records matching this query and return the patient's conditions and medications.
    ```
    *   *Failure Mode*: Hallucinated medical tests and conditions when patient records were sparse or missing.
*   **Version 2**: Instructions to register and call tools.
    ```text
    Use the search tool to locate EHR chunks. Report the patient conditions, medications, labs, and baseline values in JSON.
    ```
    *   *Failure Mode*: When the tool search yielded empty matches, the agent guessed the baseline values or extracted data from the few-shot examples (cross-contamination).
*   **Version 3**: Enforced clinical data analyst constraints, mandatory tool call execution rules, and strict instructions to log missing entries under `missing_data` instead of guessing.
    *   *Current implementation details*: Located in [prompt.json](file:///d:/Workspace/Projects/PromptProject/CliniBridge/Agents/EHR_Agent/prompt.json).

### 2.3 Production System Prompt
```json
{
  "ROLE": "You are a clinical data analyst specializing in Electronic Health Records. You receive a clinical question and a search query, then use the search_patient_data tool to find relevant EHR data. You extract and structure the findings. You do NOT diagnose. You extract data only.",
  "TASK": "Use the search_patient_data tool with data_type='ehr' to search the patient EHR. Analyze the returned chunks and structure your findings into the required JSON format."
}
```

### 2.4 Output Schema
```json
{
  "type": "object",
  "properties": {
    "conditions": { "type": "array", "items": { "type": "string" } },
    "medications": { "type": "array", "items": { "type": "string" } },
    "recent_labs": { "type": "object", "additionalProperties": { "type": "string" } },
    "relevant_notes": { "type": "string" },
    "vitals_baseline": { "type": "object", "additionalProperties": { "type": "string" } },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "missing_data": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["conditions", "medications", "recent_labs", "relevant_notes", "confidence", "missing_data"]
}
```

### 2.5 Failure Mode Analysis
*   *Observed Failure*: For a patient transferring with a sparse history (Scenario 4), the agent guessed a normal blood pressure baseline of `120/80`.
*   *Mitigation*: Added rule: `If a field is not found in the tool results, add it to missing_data. Never guess.` Verified that baseline vitals are left empty and logged appropriately.

---

## 3. Anamnesis Agent

### 3.1 Role and Task Definition
The Anamnesis Agent acts as an intake specialist. It translates patient-reported descriptions (often colloquial or symptom diaries) into standardized medical terminology, preserving the patient's subjective tone. It is trained to handle sensitive topics (e.g. mental health or drug disclosures) objectively.

### 3.2 Prompt Iteration History
*   **Version 1**: Simple text parsing instructions.
    ```text
    Read this patient journal or message. Tell me what symptoms they have and if they are taking their meds.
    ```
    *   *Failure Mode*: Summarized symptoms without logging dates or timelines. Missed medication details when the patient stated reasons for self-discontinuing.
*   **Version 2**: Structured schemas separating symptoms from medication status.
    ```text
    Parse patient records into a list of reported symptoms with severity, and medication adherence status (taking vs stopped).
    ```
    *   *Failure Mode*: Over-standardized patient vocabulary (e.g. translated "coughing all night" into a generic "respiratory symptom" without noting the character of the cough).
*   **Version 3**: Double-track symptoms (mapping clinical terms directly alongside `patient_language`), timelines, and strict adherence tracking with discontinuation reasons.
    *   *Current implementation details*: Located in [prompt.json](file:///d:/Workspace/Projects/PromptProject/CliniBridge/Agents/AnamnesisAgent/prompt.json).

### 3.3 Output Schema
```json
{
  "type": "object",
  "properties": {
    "reported_symptoms": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "symptom": { "type": "string" },
          "patient_language": { "type": "string" },
          "onset": { "type": "string" },
          "duration": { "type": "string" },
          "severity": { "type": "string" }
        },
        "required": ["symptom", "patient_language"]
      }
    },
    "medication_adherence": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "status": { "type": "string", "enum": ["taking", "stopped", "irregular"] },
          "details": { "type": "string" }
        },
        "required": ["status", "details"]
      }
    },
    "lifestyle_factors": { "type": "array", "items": { "type": "string" } },
    "family_history": { "type": "array", "items": { "type": "string" } },
    "patient_concerns": { "type": "array", "items": { "type": "string" } },
    "timeline": { "type": "array", "items": { "type": "string" } },
    "confidence": { "type": "number" },
    "missing_data": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["reported_symptoms", "medication_adherence", "timeline", "confidence", "missing_data"]
}
```

### 3.4 Failure Mode Analysis
*   *Observed Failure*: Under Scenario 5 (Conflicting Data), the patient claimed "full compliance" in intake, but the clinical lab values indicated a sub-therapeutic drug level. The agent wrote that "the patient was non-adherent," which violated neutrality.
*   *Mitigation*: Enforced bias and sensitivity rules: `Be sensitive — do not make judgments about patient behavior or choices. Report patient claims verbatim without accusing them of lying.`

---

## 4. Synthesis Agent

### 4.1 Role and Task Definition
The Synthesis Agent functions as the senior clinical informatics lead. It integrates the findings from the upstream Triage, EHR, and Anamnesis agents into the final Clinical Context Brief (CCB). Every statement must be traceably cited, and it must use non-definitive clinical language (differential reasoning) to support rather than dictate decisions.

### 4.2 Prompt Iteration History
*   **Version 1**: MONOLITHIC briefing prompt.
    ```text
    Summarize all the reports into a clinical brief. Give recommendations on what to do.
    ```
    *   *Failure Mode*: High diagnostic risk. The LLM regularly gave final diagnoses (e.g. "The patient has hypertensive crisis"). It also hallucinated source facts that did not exist in the retrievals.
*   **Version 2**: Enforced a 6-section structure and banned definitive diagnoses.
    ```text
    Return a clinical brief structured into 6 parts. Do not say the patient has a disease; instead say it might indicate.
    ```
    *   *Failure Mode*: Out-of-bounds context. The agent made recommendations without referencing whether they were backed by the EHR or the patient's anamnesis statements.
*   **Version 3**: Strict citation requirement for every analytical claim, structured recommendations with confidence levels, and a mandatory "uncertainties and gaps" section.
    *   *Current implementation details*: Located in [prompt.json](file:///d:/Workspace/Projects/PromptProject/CliniBridge/Agents/SynthesisAgent/prompt.json).

### 4.3 Production System Prompt
```json
{
  "ROLE": "You are a senior clinical informatics specialist. You receive outputs from multiple clinical agents and synthesize them into a structured Clinical Context Brief (CCB) that a clinician can read and act on in under 60 seconds.",
  "TASK": "Synthesize the alert, triage decision, EHR findings, and anamnesis findings into a complete Clinical Context Brief. Every claim must reference its source. Never invent data.",
  "SAFETY_RULES": [
    "Never make a diagnosis. Use language like may suggest, could indicate, consider.",
    "Every claim in contextual_analysis must cite its source as (EHR) or (Anamnesis) or (Alert).",
    "Never invent data. If data is missing add it to uncertainties_and_gaps.",
    "Recommended actions must be suggestions not orders. Use language like consider, suggest, may benefit from."
  ]
}
```

### 4.4 Output Schema
The output schema is structured as a JSON containing:
1.  `alert_summary`: Details of the telemetry alarm.
2.  `patient_snapshot`: Basic clinical metrics from the EHR.
3.  `contextual_analysis`: A cited summary linking the current alarm to history.
4.  `risk_assessment`: Differential clinical considerations.
5.  `recommended_actions`: Action recommendations with confidence and source tags.
6.  `uncertainties_and_gaps`: Data deficiencies (renal labs, weights, baseline values).

### 4.5 Failure Mode Analysis
*   *Observed Failure*: The Synthesis Agent suggested: "Initiate daily Lisinopril 10mg immediately," which is a prescribing decision.
*   *Mitigation*: Updated the recommended actions guardrail: `Recommended actions must be suggestions, not orders. Use conditional verbs (e.g., 'Consider restarting Lisinopril pending clinical assessment' instead of 'Restart Lisinopril').`
