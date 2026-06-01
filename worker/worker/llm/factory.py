"""
LLM factory — builds a ChatOpenAI instance pointed at DeepSeek's
OpenAI-compatible endpoint. Provider swap = config edit, no code change.
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from worker.llm.config import LLMConfig


def build_chat_model(
    cfg: LLMConfig,
    role: str,
    *,
    temperature: float | None = None,
    tags: list[str] | None = None,
) -> BaseChatModel:
    """Return a ChatOpenAI instance for the given role.

    All calls are auto-traced by LangSmith via LANGCHAIN_TRACING_V2 env var
    (set in worker.config). Per-call run_name/tags are set at invocation time.
    """
    return ChatOpenAI(
        model=cfg.model_for(role),
        api_key=cfg.deepseek_api_key,
        base_url=cfg.base_url,
        temperature=temperature if temperature is not None else cfg.temperature,
        timeout=cfg.timeout,
        max_retries=cfg.max_retries,
        tags=[*(tags or []), f"role:{role}"],
    )
