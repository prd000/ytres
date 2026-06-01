"""
LLMConfig — assembled from config.toml [llm] and env vars.

Kept separate from worker.config so tests can construct it without
requiring SUPABASE_DB_URL (which worker.config raises on if missing).
"""
from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    coordinator_model: str
    worker_model: str
    classifier_model: str
    temperature: float
    timeout: float
    max_retries: int
    embedding_model: str
    embedding_dimensions: int
    deepseek_api_key: str | None
    openai_api_key: str | None

    def model_for(self, role: str) -> str:
        models = {
            "coordinator": self.coordinator_model,
            "worker": self.worker_model,
            "classifier": self.classifier_model,
        }
        if role not in models:
            raise ValueError(f"Unknown LLM role: {role!r}. Valid roles: {list(models)}")
        return models[role]

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load from config.toml [llm] + environment variables."""
        cfg_path = Path(__file__).parent.parent.parent.parent / "config.toml"
        with open(cfg_path, "rb") as f:
            cfg = tomllib.load(f)
        l = cfg.get("llm", {})
        return cls(
            base_url=l.get("base_url", "https://api.deepseek.com/v1"),
            coordinator_model=l.get("coordinator_model", "deepseek-v4-pro"),
            worker_model=l.get("worker_model", "deepseek-v4-pro"),
            classifier_model=l.get("classifier_model", "deepseek-v4-flash"),
            temperature=l.get("temperature", 0.2),
            timeout=float(l.get("timeout", 120.0)),
            max_retries=int(l.get("max_retries", 3)),
            embedding_model=l.get("embedding_model", "text-embedding-3-small"),
            embedding_dimensions=int(l.get("embedding_dimensions", 1536)),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
        )
