"""Manual verification script for HybridRetriever (Phase 1).

Runs 5 sample queries covering different categories/filters and prints
the query, filters, and top-4 results (name, category, price, score).

Run:
    python -m rag.scripts.test_retriever
"""

from dotenv import load_dotenv

load_dotenv()

from rag.retriever import HybridRetriever

TEST_CASES = [
    ("budget laptop for students", {"category": "Laptops", "budget_max": 40000}),
    ("best camera phone", {"category": "Mobiles"}),
    ("energy efficient refrigerator", {"category": "Refrigerators", "min_rating": 4.0}),
    ("wireless earbuds with long battery life", None),
    ("gaming laptop", {"category": "Laptops", "budget_max": 100}),  # edge case: no eligible docs
]


def main() -> None:
    retriever = HybridRetriever()

    for query, filters in TEST_CASES:
        print("=" * 80)
        print(f"QUERY: {query}")
        print(f"FILTERS: {filters}")
        results = retriever.retrieve(query, filters)
        if not results:
            print("  (no results)")
            continue
        for i, item in enumerate(results, start=1):
            print(
                f"  {i}. {item['product_name'][:60]!r} | "
                f"category={item['category']} | price=Rs.{item['price']:.0f} | "
                f"rerank_score={item.get('rerank_score'):.4f}"
            )
    print("=" * 80)


if __name__ == "__main__":
    main()
