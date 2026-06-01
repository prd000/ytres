"""
LLM factory — builds a ChatOpenAI instance pointed at DeepSeek's
OpenAI-compatible endpoint. Provider swap = config edit, no code change.

Also provides invoke_structured(), a shared helper for structured-output LLM
calls that degrades gracefully from function_calling to json_mode when the
provider doesn't support tool use. Both planner and research handlers use this
so the fallback logic lives in one place.
"""
from __future__ import annotations
import logging

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from worker.llm.config import LLMConfig

log = logging.getLogger(__name__)


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


async def invoke_structured(llm: BaseChatModel, schema, messages, run_name: str):
    """Invoke LLM with structured output, degrading from function_calling to json_mode.

    Shared by planner and research handlers so the fallback path is maintained
    in one place. Both handlers pass tags/run_name at call time.
    """
    try:
        chain = llm.with_structured_output(schema, method="function_calling")
        return await chain.with_config({"run_name": run_name}).ainvoke(messages)
    except Exception as e:
        err_lower = str(e).lower()
        if any(kw in err_lower for kw in ("tool", "function", "not support", "does not support")):
            log.info("function_calling not supported by provider, retrying with json_mode")
            chain = llm.with_structured_output(schema, method="json_mode")
            return await chain.with_config({"run_name": run_name}).ainvoke(messages)
        raise
