from typing import List

from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from rag.config import EMBEDDING_MODEL


class EmbeddingManager:
    def __init__(self):
        self._model = None

    def get_embedding_model(self) -> HuggingFaceEmbedding:
        if self._model is None:
            # Load local HuggingFace embedding model on CPU
            self._model = HuggingFaceEmbedding(
                model_name=EMBEDDING_MODEL or "sentence-transformers/all-MiniLM-L6-v2",
                device="cpu"
            )
        return self._model

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string (uses the query-specific instruction prefix)."""
        return self.get_embedding_model().get_query_embedding(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts (e.g. documents for indexing)."""
        return self.get_embedding_model().get_text_embedding_batch(texts)
