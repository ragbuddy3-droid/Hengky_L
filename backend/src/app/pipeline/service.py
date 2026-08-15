"""Pipeline service for lazy loading and centralizing shared components."""
import logging
from typing import Optional, List, Dict, Any
import ollama

from app.config import get_settings
from app.retrieval.dense_index import DenseIndex
from app.retrieval.sparse_index import SparseIndex

logger = logging.getLogger(__name__)

from app.generation.llm_client import LLMClient

class PipelineService:
    _instance: Optional["PipelineService"] = None

    def __init__(self):
        self.settings = get_settings()
        self._dense_index: Optional[DenseIndex] = None
        self._llm_client: Optional[LLMClient] = None
        self._sparse_cache: Dict[str, SparseIndex] = {}
        logger.info("PipelineService initialized (provider=%s, models=%s/%s)",
                    self.settings.LLM_PROVIDER, self.settings.LLM_GENERATOR_MODEL, self.settings.LLM_JUDGE_MODEL)

    @classmethod
    def get_instance(cls) -> "PipelineService":
        if cls._instance is None:
            cls._instance = PipelineService()
        return cls._instance

    @property
    def dense_index(self) -> DenseIndex:
        if self._dense_index is None:
            logger.info("Lazy-loading DenseIndex (ChromaDB + SentenceTransformer)...")
            self._dense_index = DenseIndex(
                persist_dir=self.settings.CHROMA_PERSIST_DIR,
                collection_name="rag_aqg_chunks",
                embedding_model_name=self.settings.EMBEDDING_MODEL
            )
        return self._dense_index

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient(
                provider=self.settings.LLM_PROVIDER,
                groq_api_key=self.settings.GROQ_API_KEY,
                ollama_base_url=self.settings.OLLAMA_BASE_URL
            )
        return self._llm_client

    @property
    def ollama_client(self) -> LLMClient:
        return self.llm_client

    def create_sparse_index(self, chunks: List[Dict[str, Any]], cache_key: Optional[str] = None) -> SparseIndex:
        """Create or return cached SparseIndex (BM25) for document chunks."""
        if not cache_key and chunks:
            # Infer document_id from first chunk metadata if available
            doc_id = chunks[0].get("metadata", {}).get("document_id") if isinstance(chunks[0].get("metadata"), dict) else None
            if doc_id:
                cache_key = f"{doc_id}_{len(chunks)}"

        if cache_key and cache_key in self._sparse_cache:
            logger.info("Reusing cached SparseIndex (BM25) for key '%s'", cache_key)
            return self._sparse_cache[cache_key]

        logger.info("Building new SparseIndex (BM25) for %d chunks...", len(chunks))
        sparse = SparseIndex()
        sparse.build_index(chunks)
        
        if cache_key:
            self._sparse_cache[cache_key] = sparse
        return sparse

    def index_document_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Add chunks to dense index (ChromaDB) and invalidate sparse cache if present."""
        if not chunks:
            logger.warning("index_document_chunks called with empty chunks list")
            return
        
        formatted_chunks = []
        for c in chunks:
            formatted_chunks.append({
                "id": c["id"],
                "text": c["text"],
                "metadata": {
                    "document_id": c.get("document_id", ""),
                    "category": c.get("category", ""),
                    "chapter": c.get("chapter") or "",
                    "section_heading": c.get("section_heading") or ""
                }
            })
            
        logger.info("Indexing %d chunks into DenseIndex...", len(formatted_chunks))
        self.dense_index.index_chunks(formatted_chunks)

def get_pipeline_service() -> PipelineService:
    return PipelineService.get_instance()

