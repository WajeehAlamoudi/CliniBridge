import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EMBEDDER_CONFIG = {
    "MODEL_NAME": os.getenv("FILE_MANAGER_MODEL", "all-MiniLM-L6-v2"),
    "MODEL_CACHE_DIR": os.path.join(BASE_DIR, "data", "models", "cache"),
}
