"""Env var hygiene.

Deployment platforms (HF Spaces Secrets UI among them) can deliver secret
values with trailing newlines/whitespace, which then blow up downstream
(e.g. httpx.InvalidURL when the AstraDB endpoint ends in '\n'). Never trust
a platform secret manager to hand over clean values.
"""

import os

# Vars our code reads directly, plus vars read internally by libraries
# (langchain/groq read GROQ_API_KEY and LANGCHAIN_*/LANGSMITH_* straight
# from os.environ, so they must be cleaned in place — a wrapper at our own
# call sites can't reach those reads).
_KNOWN_VARS = (
    "ASTRA_DB_API_ENDPOINT",
    "ASTRA_DB_APPLICATION_TOKEN",
    "ASTRA_DB_KEYSPACE",
    "ASTRA_DB_COLLECTION",
    "GROQ_API_KEY",
    "MOBILE_API_KEY",
    "TECHSPECS_API_ID",
    "TECHSPECS_API_KEY",
    "TAVILY_API_KEY",
    "ALLOWED_ORIGINS",
    "HF_TOKEN",
    "OPENAI_API_KEY",
)
_KNOWN_PREFIXES = ("LANGCHAIN_", "LANGSMITH_")


def clean_env(key: str, default=None):
    """os.getenv with whitespace stripped from string values."""
    val = os.getenv(key, default)
    return val.strip() if isinstance(val, str) else val


def sanitize_env() -> None:
    """Strip whitespace in-place for all known env vars.

    Call once at startup, after load_dotenv() and before anything builds a
    client from env. Fixes reads inside third-party libs too.
    """
    for key in list(os.environ):
        if key in _KNOWN_VARS or key.startswith(_KNOWN_PREFIXES):
            stripped = os.environ[key].strip()
            if stripped != os.environ[key]:
                os.environ[key] = stripped
