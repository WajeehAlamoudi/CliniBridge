import os

EHR_AGENT_CONFIG = {
    "default_model_name": os.getenv("EHR_AGENT_MODEL", "gpt_4_1"),
    "api_key":            os.getenv("OPENROUTER_API_KEY", None),
    "max_tool_use":       int(os.getenv("EHR_MAX_TOOL_USE", "5")),
    "max_tokens":         int(os.getenv("EHR_MAX_TOKENS", "900")),
    "json_mode":          os.getenv("EHR_JSON_MODE", "true").lower() == "true",
    "temperature":        float(os.getenv("EHR_TEMPERATURE", "0.0")),
}
