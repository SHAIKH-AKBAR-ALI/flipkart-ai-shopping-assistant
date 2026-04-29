from collections import Counter

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_astradb import AstraDBVectorStore
from langchain_astradb.utils.astradb import SetupMode
from tqdm import tqdm

from flipkart import config
from flipkart.data_converter import load_documents


class DataIngestor:
    def __init__(self):
        self._embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL
        )

    def _get_vector_store(self, setup_mode: SetupMode = SetupMode.SYNC) -> AstraDBVectorStore:
        return AstraDBVectorStore(
            embedding=self._embeddings,
            collection_name=config.ASTRA_DB_COLLECTION,
            api_endpoint=config.ASTRA_DB_API_ENDPOINT,
            token=config.ASTRA_DB_APPLICATION_TOKEN,
            namespace=config.ASTRA_DB_KEYSPACE,
            setup_mode=setup_mode,
        )

    def ingest(self, load_existing: bool = True) -> AstraDBVectorStore:
        if load_existing:
            print("Loading existing vector store — skipping ingestion.")
            return self._get_vector_store(setup_mode=SetupMode.OFF)

        print("Clearing existing collection...")
        try:
            vector_store.clear()
            print("Collection cleared.")
        except Exception as e:
            print(f"Warning: Could not clear collection: {e}. Proceeding anyway.")

        documents = load_documents()
        if not documents:
            raise RuntimeError("No documents loaded. Check data/ CSV files.")

        batch_size = 50
        batches = [documents[i : i + batch_size] for i in range(0, len(documents), batch_size)]

        for batch in tqdm(batches, desc="Ingesting batches", unit="batch"):
            vector_store.add_documents(batch)

        print(f"\nIngestion complete. Total docs: {len(documents)}")

        category_counts = Counter(doc.metadata["category"] for doc in documents)
        print("\nCategory breakdown:")
        for cat, count in sorted(category_counts.items()):
            print(f"  {cat}: {count}")

        return vector_store
