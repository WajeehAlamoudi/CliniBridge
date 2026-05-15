import os

TRIAGE_AGENT_CONFIG = {
    "default_model_name": os.getenv("TRIAGE_AGENT_MODEL", "gpt_4_1"),
    "api_key":            os.getenv("OPENROUTER_API_KEY", None),
    "max_tool_use":       int(os.getenv("TRIAGE_MAX_TOOL_USE", "13")),
    "max_tokens":         int(os.getenv("TRIAGE_MAX_TOKENS", "900")),
    "json_mode":          os.getenv("TRIAGE_JSON_MODE", "true").lower() == "true",
    "temperature":        float(os.getenv("TRIAGE_TEMPERATURE", "0.1")),
}
