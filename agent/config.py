"""
Central config: reads secrets from environment variables.
In Colab these came from `userdata.get(...)`; in a container they're
passed in via `docker run -e VAR=value` or the platform's env-var settings.
"""
import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

DB_PATH = os.environ.get("GOVERNANCE_DB_PATH", "governance.db")

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is not set. Agent LLM calls will fail.")
