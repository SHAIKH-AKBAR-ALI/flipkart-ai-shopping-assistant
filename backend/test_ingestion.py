import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from flipkart.data_converter import load_documents
from flipkart.data_ingestion import DataIngestor


def main():
    print("=" * 60)
    print("Loading documents from CSV...")
    documents = load_documents()
    print(f"Documents loaded from CSV: {len(documents)}")

    if not documents:
        print("ERROR: No documents loaded. Check data/flipkart_product_review.csv exists.")
        sys.exit(1)

    print("\nSample document:")
    sample = documents[0]
    print(f"  page_content: {sample.page_content[:200]}...")
    print(f"  metadata:")
    for k, v in sample.metadata.items():
        print(f"    {k}: {v}")

    print("\n" + "=" * 60)
    print("Connecting to AstraDB and ingesting documents...")
    print("(This may take a few minutes for large datasets)")
    print("=" * 60)

    ingestor = DataIngestor()
    vector_store = ingestor.ingest(load_existing=False)

    print("\nAstraDB connection: OK")

    print("\nVerifying with similarity search...")
    test_results = vector_store.similarity_search("bluetooth headphones", k=3)
    print(f"Test search returned {len(test_results)} results.")
    if test_results:
        print(f"  Top result: {test_results[0].metadata.get('product_name', 'N/A')}")

    print("\n" + "=" * 60)
    print("Ingestion complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
