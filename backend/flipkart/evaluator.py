import math
import asyncio
import concurrent.futures

_ZERO_SCORES = {
    "faithfulness": 0.0,
    "answer_relevancy": 0.0,
    "context_precision": 0.0,
    "context_recall": 0.0,
}

_RAGAS_TIMEOUT = 30


def _safe_score(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, float) and math.isnan(val):
        return 0.0
    return round(float(val), 3)


def _run_ragas_sync(query: str, answer: str, contexts: list[str]) -> dict:
    try:
        from datasets import Dataset
        from langchain_groq import ChatGroq
        from ragas import evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        from flipkart import config

        ragas_llm = LangchainLLMWrapper(
            ChatGroq(
                model=config.LLM_MODEL,
                api_key=config.GROQ_API_KEY,
                temperature=0.1,
            )
        )

        metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
        for m in metrics:
            m.llm = ragas_llm

        data = Dataset.from_dict({
            "question": [query],
            "answer": [answer],
            "contexts": [contexts],
            "ground_truth": [answer],
        })

        result = evaluate(dataset=data, metrics=metrics, raise_exceptions=False)
        df = result.to_pandas()
        row = df.iloc[0]

        return {
            "faithfulness": _safe_score(row.get("faithfulness")),
            "answer_relevancy": _safe_score(row.get("answer_relevancy")),
            "context_precision": _safe_score(row.get("context_precision")),
            "context_recall": _safe_score(row.get("context_recall")),
        }
    except Exception:
        return _ZERO_SCORES.copy()


class RAGEvaluator:
    def __init__(self):
        self._available = self._check_ragas()

    def _check_ragas(self) -> bool:
        try:
            import ragas  # noqa: F401
            from datasets import Dataset  # noqa: F401
            return True
        except ImportError:
            return False

    def evaluate(self, query: str, answer: str, contexts: list[str]) -> dict:
        """Synchronous evaluate — blocks caller. Use evaluate_async for non-blocking."""
        if not self._available or not contexts:
            return _ZERO_SCORES.copy()
        return _run_ragas_sync(query, answer, contexts)

    async def evaluate_async(self, query: str, answer: str, contexts: list[str]) -> dict:
        """Run RAGAS in a thread with a 30s timeout. Never raises."""
        if not self._available or not contexts:
            return _ZERO_SCORES.copy()
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_run_ragas_sync, query, answer, contexts),
                timeout=_RAGAS_TIMEOUT,
            )
        except Exception:
            return _ZERO_SCORES.copy()
