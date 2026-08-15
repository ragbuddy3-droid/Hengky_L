"""Dense vector retrieval using ChromaDB."""
import time
import logging
import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class DenseIndex:
    def __init__(self, persist_dir: str, collection_name: str, embedding_model_name: str):
        logger.info("Initializing DenseIndex (collection='%s', model='%s', dir='%s')",
                    collection_name, embedding_model_name, persist_dir)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.model = SentenceTransformer(embedding_model_name)
        logger.info("DenseIndex ready (existing docs in collection: %d)", self.collection.count())
        
    def index_chunks(self, chunks: list[dict]) -> None:
        """Add chunks to ChromaDB collection with metadata."""
        if not chunks:
            logger.warning("index_chunks called with empty chunk list, skipping")
            return
        
        logger.info("Indexing %d chunks into ChromaDB...", len(chunks))
        start_time = time.time()
        
        texts = [c['text'] for c in chunks]
        
        logger.info("  Encoding embeddings for %d texts...", len(texts))
        encode_start = time.time()
        embeddings = self.model.encode(texts).tolist()
        encode_elapsed = time.time() - encode_start
        logger.info("  Embedding encoding complete in %.2fs", encode_elapsed)
        
        ids = [c['id'] for c in chunks]
        metadatas = [c.get('metadata', {}) for c in chunks]
        
        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )
        
        elapsed = time.time() - start_time
        logger.info("Indexed %d chunks in %.2fs (total in collection: %d)",
                    len(chunks), elapsed, self.collection.count())
        
    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        """Query by embedding similarity."""
        truncated_query = query_text[:80] + "..." if len(query_text) > 80 else query_text
        logger.info("Dense query (top_k=%d): '%s'", top_k, truncated_query)
        
        start_time = time.time()
        query_embedding = self.model.encode([query_text]).tolist()
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k
        )
        
        output = []
        if results['documents'] and results['documents'][0]:
            for i in range(len(results['documents'][0])):
                output.append({
                    "id": results['ids'][0][i],
                    "text": results['documents'][0][i],
                    "score": results['distances'][0][i] if results['distances'] else 0.0,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
                })
        
        elapsed = time.time() - start_time
        top_score = output[0]['score'] if output else 0.0
        logger.info("Dense query returned %d results in %.3fs (top_score=%.4f)",
                    len(output), elapsed, top_score)
        return output
        
    def delete_by_document(self, document_id: str) -> None:
        """Remove all chunks for a document."""
        logger.info("Deleting chunks for document_id='%s' from ChromaDB", document_id)
        self.collection.delete(
            where={"document_id": document_id}
        )
        logger.info("Deletion complete for document_id='%s'", document_id)
