import os
from dotenv import load_dotenv

load_dotenv()


# ─── LLM ──────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv(
    "ANTHROPIC_API_KEY",
    ""
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MODEL = os.getenv(
    "MODEL",
    "claude-sonnet-4-6"
)


# ─── Web Search ────────────────────────────────────────────────────────────────

TAVILY_API_KEY = os.getenv(
    "TAVILY_API_KEY",
    ""
)

SERPER_API_KEY = os.getenv(
    "SERPER_API_KEY",
    ""
)

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")


# ─── Database ─────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    ""
)


# ─── Authentication ───────────────────────────────────────────────────────────

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    ""
)

SUPABASE_JWT_SECRET = os.getenv(
    "SUPABASE_JWT_SECRET",
    ""
)

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
)