import os

SYNTHESIS_AGENT_CONFIG = {
    "default_model_name": os.getenv("SYNTHESIS_AGENT_MODEL", "gpt_4_1"),
    "api_key":            os.getenv("OPENROUTER_API_KEY", None),
    "max_tool_use":       int(os.getenv("SYNTHESIS_MAX_TOOL_USE", "5")),
    "max_tokens":         int(os.getenv("SYNTHESIS_MAX_TOKENS", "2000")),
    "json_mode":          os.getenv("SYNTHESIS_JSON_MODE", "true").lower() == "true",
    "temperature":        float(os.getenv("SYNTHESIS_TEMPERATURE", "0.2")),
}
