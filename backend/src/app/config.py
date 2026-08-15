"""Configuration management for RAG-AQG v3 strictly from YAML."""

import os
import logging
from functools import lru_cache
from typing import List, Optional
import yaml
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


def find_yaml_config() -> str:
    """Find settings.yaml location."""
    candidates = [
        "configs/settings.yaml",
        "backend/configs/settings.yaml",
        os.path.join(os.path.dirname(__file__), "../../configs/settings.yaml"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    raise FileNotFoundError(
        "Configuration file 'configs/settings.yaml' not found. "
        "All application settings must be defined in configs/settings.yaml."
    )


class Settings(BaseModel):
    """Application settings loaded strictly from central YAML configuration."""

    LLM_PROVIDER: str
    GROQ_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: str
    LLM_GENERATOR_MODEL: str
    LLM_JUDGE_MODEL: str
    EMBEDDING_MODEL: str
    GROUNDING_THRESHOLD: float
    GROUNDING_AUTO_PASS_THRESHOLD: float
    MAX_REFINEMENT_ATTEMPTS: int
    DATABASE_URL: str
    CHROMA_PERSIST_DIR: str
    BACKEND_HOST: str
    BACKEND_PORT: int
    FRONTEND_PORT: int
    CORS_ORIGINS: List[str]
    RETRIEVAL_TOP_K: int
    HYBRID_DENSE_WEIGHT: float
    HYBRID_SPARSE_WEIGHT: float

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def load_from_yaml(cls, yaml_path: Optional[str] = None) -> "Settings":
        """Load and parse settings strictly from the central YAML configuration file."""
        path = yaml_path or find_yaml_config()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            raise ValueError(f"YAML config file at {path} is empty or invalid.")

        flat = {}
        if "app" in data:
            app = data["app"]
            if "backend_host" in app: flat["BACKEND_HOST"] = str(app["backend_host"])
            if "backend_port" in app: flat["BACKEND_PORT"] = int(app["backend_port"])
            if "frontend_port" in app: flat["FRONTEND_PORT"] = int(app["frontend_port"])
            if "cors_origins" in app: flat["CORS_ORIGINS"] = list(app["cors_origins"])

        if "llm" in data:
            llm = data["llm"]
            if "provider" in llm: flat["LLM_PROVIDER"] = str(llm["provider"])
            if "groq_api_key" in llm: flat["GROQ_API_KEY"] = str(llm["groq_api_key"]) if llm["groq_api_key"] else None
            if "ollama_base_url" in llm: flat["OLLAMA_BASE_URL"] = str(llm["ollama_base_url"])
            if "generator_model" in llm: flat["LLM_GENERATOR_MODEL"] = str(llm["generator_model"])
            if "judge_model" in llm: flat["LLM_JUDGE_MODEL"] = str(llm["judge_model"])
            if "embedding_model" in llm: flat["EMBEDDING_MODEL"] = str(llm["embedding_model"])

        if "validation" in data:
            val = data["validation"]
            if "grounding_threshold" in val: flat["GROUNDING_THRESHOLD"] = float(val["grounding_threshold"])
            if "grounding_auto_pass_threshold" in val: flat["GROUNDING_AUTO_PASS_THRESHOLD"] = float(val["grounding_auto_pass_threshold"])
            if "max_refinement_attempts" in val: flat["MAX_REFINEMENT_ATTEMPTS"] = int(val["max_refinement_attempts"])

        if "database" in data:
            db = data["database"]
            if "url" in db: flat["DATABASE_URL"] = str(db["url"])
            if "chroma_persist_dir" in db: flat["CHROMA_PERSIST_DIR"] = str(db["chroma_persist_dir"])

        if "retrieval" in data:
            ret = data["retrieval"]
            if "top_k" in ret: flat["RETRIEVAL_TOP_K"] = int(ret["top_k"])
            if "hybrid_dense_weight" in ret: flat["HYBRID_DENSE_WEIGHT"] = float(ret["hybrid_dense_weight"])
            if "hybrid_sparse_weight" in ret: flat["HYBRID_SPARSE_WEIGHT"] = float(ret["hybrid_sparse_weight"])

        logger.info("Successfully loaded configuration strictly from YAML: %s", path)
        return cls(**flat)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance strictly derived from central YAML configuration."""
    return Settings.load_from_yaml()


