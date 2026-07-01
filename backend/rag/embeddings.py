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
