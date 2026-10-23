"""Configuration: configs/settings.yaml for settings, .env for secrets. Relative paths resolve against backend/."""

import logging
import os
from functools import cache
from pathlib import Path
from typing import Any

import dotenv
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_DIR / ".env"
YAML_FILE = BACKEND_DIR / "configs" / "settings.yaml"


def _resolve(path: str | Path) -> Path:
    """A relative path is taken from backend/, so the app behaves the same whatever the working directory."""
    p = Path(path)
    return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


class AppConfig(BaseModel):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class LLMConfig(BaseModel):
    provider: str = "deepinfra"
    # validate_default so the .env fallback below runs when the YAML omits the key
    deepinfra_api_key: str | None = Field(default=None, validate_default=True)
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
        return v or os.environ.get("DEEPINFRA_API_KEY")


class ValidationConfig(BaseModel):
    fast_reject_threshold: float = 0.40
    max_refinement_attempts: int = 3


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data/rag_aqg.db"
    chroma_persist_dir: str = "./data/chroma"

    @field_validator("url")
    @classmethod
    def resolve_sqlite_path(cls, v: str) -> str:
        prefix = "sqlite:///"
        if v.startswith(prefix) and v != prefix and not v.startswith(prefix + ":memory:"):
            return prefix + _resolve(v[len(prefix):]).as_posix()
        return v

    @field_validator("chroma_persist_dir")
    @classmethod
    def resolve_chroma_dir(cls, v: str) -> str:
        return str(_resolve(v))

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")


class RetrievalConfig(BaseModel):
    candidate_top_k: int = 15
    hybrid_dense_weight: float = 0.6
    hybrid_sparse_weight: float = 0.4
    max_questions_per_chunk: int = 3  # upper bound of a chunk's question capacity
    min_relative_score: float = 0.5  # drop topic candidates scoring below this fraction of the best one
    reserve_chunks: int = 3  # extra ranked chunks for capacity expansion and the top-up round


class GenerationConfig(BaseModel):
    concurrency: int = 5  # max parallel LLM work items (generation & validation)
    max_context_chunks: int = 10  # upper bound of the chunk budget


class AuthConfig(BaseModel):
    jwt_secret: str | None = Field(default=None, validate_default=True)  # from .env JWT_SECRET; falls back to a generated secret in data/
    session_days: int = 7  # login lifetime without "Ingat saya"
    remember_days: int = 30  # login lifetime with "Ingat saya"
    guest_ttl_hours: int = 24  # inactive guest data is purged after this
    session_cookie: str = "soalnya_session"
    guest_cookie: str = "soalnya_guest"
    cookie_secure: bool = False  # True when served over HTTPS

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def resolve_env_var(cls, v: Any) -> Any:
        return v or os.environ.get("JWT_SECRET")


class ChunkingConfig(BaseModel):
    fixed_chunk_size: int = 1000
    fixed_chunk_overlap: int = 150


class PathsConfig(BaseModel):
    data_dir: Path = Field(default=Path("data"), validate_default=True)

    @field_validator("data_dir")
    @classmethod
    def resolve_data_dir(cls, v: Path) -> Path:
        return _resolve(v)

    @property
    def raw_dir(self) -> Path:
        """Uploaded PDFs."""
        return self.data_dir / "raw"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def jwt_secret_file(self) -> Path:
        return self.data_dir / ".jwt_secret"


class Settings(BaseModel):
    """Application settings loaded from the central YAML configuration."""

    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def load(cls, yaml_path: Path = YAML_FILE) -> "Settings":
        """Load .env into the environment (existing variables win), then parse the YAML."""
        dotenv.load_dotenv(ENV_FILE, override=False)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if not data or not isinstance(data, dict):
            raise ValueError(f"YAML config file at {yaml_path} is empty or invalid.")

        settings = cls.model_validate(data)
        logger.info("Loaded configuration from %s (provider: %s)", yaml_path, settings.llm.provider)
        return settings


@cache
def get_settings() -> Settings:
    return Settings.load()
