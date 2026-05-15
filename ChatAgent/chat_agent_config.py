import os

CHAT_AGENT_CONFIG = {
    "models": {
        "gpt_4_1": os.getenv("MODEL_GPT_4_1", "openai/gpt-4.1"),
        "claude_sonnet_4_5": os.getenv("MODEL_CLAUDE_SONNET_4_5", "anthropic/claude-sonnet-4.5"),
        "llama_3_3_70b_instruct": os.getenv("MODEL_LLAMA_3_3_70B_INSTRUCT", "meta-llama/llama-3.3-70b-instruct"),
        "gemini_2_5_pro_preview": os.getenv("MODEL_GEMINI_2_5_PRO_PREVIEW", "google/gemini-2.5-pro-preview"),
        "deepseek_chat_v3_0324": os.getenv("MODEL_DEEPSEEK_CHAT_V3_0324", "deepseek/deepseek-chat-v3-0324"),
        "mistral_large_2411": os.getenv("MODEL_MISTRAL_LARGE_2411", "mistralai/mistral-large-2411"),
        "qwen_2_5_72b_instruct": os.getenv("MODEL_QWEN_2_5_72B_INSTRUCT", "qwen/qwen-2.5-72b-instruct"),
    },
    "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),

    "max_tokens": int(os.getenv("CHAT_AGENT_MAX_TOKENS", "900")),
    "max_tool_use": int(os.getenv("CHAT_AGENT_MAX_TOOL_USE", "13")),
    "default_model_name": os.getenv("CHAT_AGENT_DEFAULT_MODEL", "gpt_4_1"),

    "http_referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost"),
    "app_title": os.getenv("OPENROUTER_APP_TITLE", "DBAnalyst_Agent"),
}
