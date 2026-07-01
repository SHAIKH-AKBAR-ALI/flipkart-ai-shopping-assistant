"""Create a fresh AstraDB collection for the V2 RAG pipeline.

Reads credentials from environment variables (backend/.env):
  ASTRA_DB_API_ENDPOINT
  ASTRA_DB_APPLICATION_TOKEN
  ASTRA_DB_KEYSPACE (optional, defaults to "default_keyspace")
  ASTRA_DB_COLLECTION

Vector dimension = 384 (sentence-transformers/all-MiniLM-L6-v2)
Similarity metric = cosine

Run:
    python -m rag.scripts.create_collection
"""

import os
import sys

from astrapy import DataAPIClient
from astrapy.constants import VectorMetric
from dotenv import load_dotenv

load_dotenv()

VECTOR_DIMENSION = 384
SIMILARITY_METRIC = VectorMetric.COSINE


def main() -> None:
    endpoint = os.environ.get("ASTRA_DB_API_ENDPOINT")
    token = os.environ.get("ASTRA_DB_APPLICATION_TOKEN")
    keyspace = os.environ.get("ASTRA_DB_KEYSPACE", "default_keyspace")
    collection_name = os.environ.get("ASTRA_DB_COLLECTION")

    missing = [
        name
        for name, val in [
            ("ASTRA_DB_API_ENDPOINT", endpoint),
            ("ASTRA_DB_APPLICATION_TOKEN", token),
            ("ASTRA_DB_COLLECTION", collection_name),
        ]
        if not val
    ]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    client = DataAPIClient(token)
    database = client.get_database(endpoint, keyspace=keyspace)

    collection = database.create_collection(
        collection_name,
        dimension=VECTOR_DIMENSION,
        metric=SIMILARITY_METRIC,
    )

    print(f"Collection created: {collection.name}")
    print(f"Keyspace: {keyspace}")
    print(f"Dimension: {VECTOR_DIMENSION}, Metric: {SIMILARITY_METRIC}")

    info = database.list_collections()
    names = [c.name for c in info]
    print(f"Collections now in keyspace: {names}")
    assert collection_name in names, "Collection not found in list_collections() after creation"
    print("Confirmed via API response.")


if __name__ == "__main__":
    main()
