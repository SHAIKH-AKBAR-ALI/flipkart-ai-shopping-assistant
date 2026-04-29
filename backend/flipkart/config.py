import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ASTRA_DB_API_ENDPOINT = os.getenv("ASTRA_DB_API_ENDPOINT")
ASTRA_DB_APPLICATION_TOKEN = os.getenv("ASTRA_DB_APPLICATION_TOKEN")
ASTRA_DB_KEYSPACE = os.getenv("ASTRA_DB_KEYSPACE")
ASTRA_DB_COLLECTION = os.getenv("ASTRA_DB_COLLECTION")

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "llama-3.3-70b-versatile"
RETRIEVER_K = 6
RERANK_TOP_N = 4
HISTORY_WINDOW = 6

_REQUIRED = {
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "GROQ_API_KEY": GROQ_API_KEY,
    "ASTRA_DB_API_ENDPOINT": ASTRA_DB_API_ENDPOINT,
    "ASTRA_DB_APPLICATION_TOKEN": ASTRA_DB_APPLICATION_TOKEN,
    "ASTRA_DB_KEYSPACE": ASTRA_DB_KEYSPACE,
    "ASTRA_DB_COLLECTION": ASTRA_DB_COLLECTION,
}

_missing = [k for k, v in _REQUIRED.items() if not v]
if _missing:
    raise ValueError(f"Missing required environment variables: {', '.join(_missing)}")
