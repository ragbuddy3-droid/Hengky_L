"""Configuration management for RAG-AQG with YAML settings and .env secrets."""

import logging
import os
from functools import lru_cache
from typing import Any

import dotenv
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


def load_environment_variables() -> None:
    """Load environment variables from .env file."""
    candidates = [
        ".env",
        "backend/.env",
        os.path.join(os.path.dirname(__file__), "../../../.env"),
        os.path.join(os.path.dirname(__file__), "../../.env"),
    ]
    for c in candidates:
        if os.path.exists(c):
            dotenv.load_dotenv(dotenv_path=os.path.abspath(c), override=False)
            logger.info("Loaded .env from: %s", os.path.abspath(c))
            break
    else:
        dotenv.load_dotenv()


def find_yaml_config() -> str:
    """Find settings.yaml location dynamically."""
    candidates = [
        "configs/settings.yaml",
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
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class LLMConfig(BaseModel):
    provider: str = "deepinfra"
    deepinfra_api_key: str | None = None
    deepinfra_base_url: str = "https://api.deepinfra.com/v1/openai"
    generator_model: str = "Qwen/Qwen3-32B"
    judge_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    embedding_model: str = "BAAI/bge-m3"
    max_tokens: int = 4096
    request_timeout: int = 60  # seconds per LLM call; a hung call otherwise stalls the whole batch
    max_retries: int = 2

    @field_validator("deepinfra_api_key", mode="before")
    @classmethod
    def resolve_env_var(cls, v: Any) -> Any:
        """Resolve API token strictly from environment (.env) if omitted or placeholder."""
        if not v or (isinstance(v, str) and v.startswith("${") and v.endswith("}")):
            return os.environ.get("DEEPINFRA_API_KEY") or os.environ.get("DEEPINFRA_TOKEN")
        return v



class ValidationConfig(BaseModel):
    fast_reject_threshold: float = 0.40
    max_refinement_attempts: int = 3


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data/rag_aqg.db"
    chroma_persist_dir: str = "./data/chroma"


class RetrievalConfig(BaseModel):
    candidate_top_k: int = 15
    hybrid_dense_weight: float = 0.6
    hybrid_sparse_weight: float = 0.4
    reranker_enabled: bool = True
    max_questions_per_chunk: int = 3  # upper bound of a chunk's question capacity
    min_relative_score: float = 0.5  # drop topic candidates scoring below this fraction of the best one
    reserve_chunks: int = 3  # extra ranked chunks for capacity expansion and the top-up round


class GenerationConfig(BaseModel):
    concurrency: int = 5  # max parallel LLM work items (generation & validation)
    max_context_chunks: int = 10  # upper bound of the chunk budget


class ChunkingConfig(BaseModel):
    strategy: str = "fixed"
    fixed_chunk_size: int = 1000
    fixed_chunk_overlap: int = 150



class Settings(BaseModel):
    """Application settings loaded strictly from central YAML configuration."""

    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)

    model_config = ConfigDict(extra="ignore")

    # Convenient backward-compatible uppercase properties
    @property
    def BACKEND_HOST(self) -> str:
        return self.app.backend_host

    @property
    def BACKEND_PORT(self) -> int:
        return self.app.backend_port

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return self.app.cors_origins

    @property
    def LLM_PROVIDER(self) -> str:
        return self.llm.provider

    @property
    def DEEPINFRA_API_KEY(self) -> str | None:
        return self.llm.deepinfra_api_key or os.environ.get("DEEPINFRA_API_KEY") or os.environ.get("DEEPINFRA_TOKEN")

    @property
    def DEEPINFRA_BASE_URL(self) -> str:
        return self.llm.deepinfra_base_url

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
    def MAX_TOKENS(self) -> int:
        return self.llm.max_tokens

    @property
    def LLM_REQUEST_TIMEOUT(self) -> int:
        return self.llm.request_timeout

    @property
    def LLM_MAX_RETRIES(self) -> int:
        return self.llm.max_retries

    @property
    def FAST_REJECT_THRESHOLD(self) -> float:
        return self.validation.fast_reject_threshold

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
    def CANDIDATE_TOP_K(self) -> int:
        return self.retrieval.candidate_top_k

    @property
    def MAX_QUESTIONS_PER_CHUNK(self) -> int:
        return self.retrieval.max_questions_per_chunk

    @property
    def MIN_RELATIVE_SCORE(self) -> float:
        return self.retrieval.min_relative_score

    @property
    def RESERVE_CHUNKS(self) -> int:
        return self.retrieval.reserve_chunks

    @property
    def RERANKER_ENABLED(self) -> bool:
        return self.retrieval.reranker_enabled

    @property
    def HYBRID_DENSE_WEIGHT(self) -> float:
        return self.retrieval.hybrid_dense_weight

    @property
    def HYBRID_SPARSE_WEIGHT(self) -> float:
        return self.retrieval.hybrid_sparse_weight

    @property
    def GENERATION_CONCURRENCY(self) -> int:
        return self.generation.concurrency

    @property
    def MAX_CONTEXT_CHUNKS(self) -> int:
        return self.generation.max_context_chunks

    @classmethod
    def load_from_yaml(cls, yaml_path: str | None = None) -> "Settings":
        """Load and parse settings from YAML and environment (.env)."""
        load_environment_variables()
        path = yaml_path or find_yaml_config()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            raise ValueError(f"YAML config file at {path} is empty or invalid.")

        settings = cls.model_validate(data)
        logger.info("Successfully loaded configuration from YAML: %s (Provider: %s)", path, settings.llm.provider)
        return settings


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance strictly derived from central YAML configuration."""
    return Settings.load_from_yaml()
