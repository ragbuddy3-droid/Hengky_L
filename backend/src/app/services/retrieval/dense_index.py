"""Dense retrieval index using ChromaDB vector database and sentence-transformers."""

import logging
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class DenseIndex:
    """Vector index powered by ChromaDB persistent storage and SentenceTransformer."""

    def __init__(
        self,
        persist_dir: str = "./data/chroma",
        collection_name: str = "rag_aqg_chunks",
        embedding_model_name: str = "BAAI/bge-m3"
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name

        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        logger.info("Initializing DenseIndex with model '%s' in '%s'...", embedding_model_name, persist_dir)

        self._model = SentenceTransformer(embedding_model_name)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("DenseIndex initialized. Current collection count: %d", self.collection.count())

    @property
    def model(self) -> SentenceTransformer:
        """Access underlying SentenceTransformer model (e.g. for grounding validation)."""
        return self._model

    def index_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Encode chunks and insert into ChromaDB."""
        if not chunks:
            logger.warning("DenseIndex: empty chunks received for indexing.")
            return

        texts = [c["text"] for c in chunks]
        ids = [c["id"] for c in chunks]
        metadatas = [
            {
                "document_id": str(c.get("metadata", {}).get("document_id") or c.get("document_id") or ""),
                "category": str(c.get("metadata", {}).get("category") or c.get("category") or ""),
                "chapter": str(c.get("metadata", {}).get("chapter") or c.get("chapter") or ""),
                "section_heading": str(c.get("metadata", {}).get("section_heading") or c.get("section_heading") or ""),
            }
            for c in chunks
        ]

        logger.info("Encoding %d chunks with %s...", len(texts), self.embedding_model_name)
        embeddings = self._model.encode(texts, show_progress_bar=False, normalize_embeddings=True).tolist()

        # Batch upsert to prevent exceeding limits
        batch_size = 200
        for i in range(0, len(ids), batch_size):
            end_idx = i + batch_size
            self.collection.upsert(
                ids=ids[i:end_idx],
                embeddings=embeddings[i:end_idx],
                documents=texts[i:end_idx],
                metadatas=metadatas[i:end_idx],
            )

        logger.info("Successfully indexed %d chunks in ChromaDB.", len(chunks))

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Query ChromaDB vector store and return ranked chunks."""
        if not query_text or not query_text.strip() or self.collection.count() == 0:
            return []

        query_emb = self._model.encode([query_text], normalize_embeddings=True).tolist()
        results = self.collection.query(
            query_embeddings=query_emb,
            n_results=min(top_k, self.collection.count()),
            include=["documents", "metadatas", "distances"]
        )

        output: list[dict[str, Any]] = []
        if results and results["ids"] and len(results["ids"][0]) > 0:
            for idx in range(len(results["ids"][0])):
                chunk_id = results["ids"][0][idx]
                doc_text = results["documents"][0][idx]
                metadata = results["metadatas"][0][idx] if results["metadatas"] else {}
                dist = results["distances"][0][idx] if results["distances"] else 0.0
                score = 1.0 - dist  # Cosine similarity score

                output.append({
                    "id": chunk_id,
                    "text": doc_text,
                    "score": score,
                    "metadata": metadata,
                })

        return output

    def delete_by_document(self, document_id: str) -> None:
        """Delete all chunks belonging to a document."""
        try:
            self.collection.delete(where={"document_id": document_id})
            logger.info("Deleted vectors for document_id '%s' from ChromaDB.", document_id)
        except Exception as e:
            logger.warning("Error deleting vectors for document_id '%s': %s", document_id, e)
