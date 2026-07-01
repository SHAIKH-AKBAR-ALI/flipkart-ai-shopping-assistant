"""Throwaway connectivity check for the new AstraDB collection.

Connects using backend/.env values and confirms the collection is
reachable by counting documents (expect 0 on a fresh collection).

Run:
    python -m rag.scripts.verify_connectivity
"""

import os
import sys

from astrapy import DataAPIClient
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    endpoint = os.environ.get("ASTRA_DB_API_ENDPOINT")
    token = os.environ.get("ASTRA_DB_APPLICATION_TOKEN")
    keyspace = os.environ.get("ASTRA_DB_KEYSPACE", "default_keyspace")
    collection_name = os.environ.get("ASTRA_DB_COLLECTION")

    if not all([endpoint, token, collection_name]):
        print("Missing required ASTRA_DB_* env vars", file=sys.stderr)
        sys.exit(1)

    client = DataAPIClient(token)
    database = client.get_database(endpoint, keyspace=keyspace)
    collection = database.get_collection(collection_name)

    count = collection.count_documents(filter={}, upper_bound=1000)
    print(f"Connected to collection '{collection_name}' in keyspace '{keyspace}'.")
    print(f"Document count: {count}")


if __name__ == "__main__":
    main()
