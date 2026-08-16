"""Configuration management for RAG-AQG strictly from YAML (No .env)."""

import os
import logging
from functools import lru_cache
from typing import List, Optional
import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


def find_yaml_config() -> str:
    """Find settings.yaml location dynamically."""
    candidates = [
        "configs/settings.yaml",
        "backend_new/configs/settings.yaml",
        "backend/configs/settings.yaml",
        os.path.join(os.path.dirname(__file__), "../../../configs/settings.yaml"),
        os.path.join(os.path.dirname(__file__), "../../configs/settings.yaml"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    raise FileNotFoundError(
        "Configuration file 'configs/settings.yaml' not found. "
        "All application settings must be defined in configs/settings.yaml."
    )


class AppConfig(BaseModel):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_port: int = 3000
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class LLMConfig(BaseModel):
    provider: str = "groq"
    groq_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"
    generator_model: str = "qwen/qwen3.6-27b"
    judge_model: str = "qwen/qwen3.6-27b"
    embedding_model: str = "BAAI/bge-m3"


class ValidationConfig(BaseModel):
    grounding_threshold: float = 0.50
    grounding_auto_pass_threshold: float = 0.80
    max_refinement_attempts: int = 3


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data/rag_aqg.db"
    chroma_persist_dir: str = "./data/chroma"


class RetrievalConfig(BaseModel):
    top_k: int = 5
    hybrid_dense_weight: float = 0.6
    hybrid_sparse_weight: float = 0.4


class ChunkingConfig(BaseModel):
    fixed_chunk_size: int = 1000
    fixed_chunk_overlap: int = 150
    semantic_breakpoint_type: str = "percentile"
    semantic_breakpoint_threshold: float = 95.0


class Settings(BaseModel):
    """Application settings loaded strictly from central YAML configuration."""

    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)

    model_config = ConfigDict(extra="ignore")

    # Convenient backward-compatible uppercase properties
    @property
    def BACKEND_HOST(self) -> str:
        return self.app.backend_host

    @property
    def BACKEND_PORT(self) -> int:
        return self.app.backend_port

    @property
    def FRONTEND_PORT(self) -> int:
        return self.app.frontend_port

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return self.app.cors_origins

    @property
    def LLM_PROVIDER(self) -> str:
        return self.llm.provider

    @property
    def GROQ_API_KEY(self) -> Optional[str]:
        return self.llm.groq_api_key

    @property
    def OLLAMA_BASE_URL(self) -> str:
        return self.llm.ollama_base_url

    @property
    def LLM_GENERATOR_MODEL(self) -> str:
        return self.llm.generator_model

    @property
    def LLM_JUDGE_MODEL(self) -> str:
        return self.llm.judge_model

    @property
    def EMBEDDING_MODEL(self) -> str:
        return self.llm.embedding_model

    @property
    def GROUNDING_THRESHOLD(self) -> float:
        return self.validation.grounding_threshold

    @property
    def GROUNDING_AUTO_PASS_THRESHOLD(self) -> float:
        return self.validation.grounding_auto_pass_threshold

    @property
    def MAX_REFINEMENT_ATTEMPTS(self) -> int:
        return self.validation.max_refinement_attempts

    @property
    def DATABASE_URL(self) -> str:
        return self.database.url

    @property
    def CHROMA_PERSIST_DIR(self) -> str:
        return self.database.chroma_persist_dir

    @property
    def RETRIEVAL_TOP_K(self) -> int:
        return self.retrieval.top_k

    @property
    def HYBRID_DENSE_WEIGHT(self) -> float:
        return self.retrieval.hybrid_dense_weight

    @property
    def HYBRID_SPARSE_WEIGHT(self) -> float:
        return self.retrieval.hybrid_sparse_weight

    @classmethod
    def load_from_yaml(cls, yaml_path: Optional[str] = None) -> "Settings":
        """Load and parse settings strictly from the central YAML configuration file."""
        path = yaml_path or find_yaml_config()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            raise ValueError(f"YAML config file at {path} is empty or invalid.")

        settings = cls.model_validate(data)
        logger.info("Successfully loaded configuration strictly from YAML: %s", path)
        return settings


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance strictly derived from central YAML configuration."""
    return Settings.load_from_yaml()
