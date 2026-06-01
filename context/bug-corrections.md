# Bug Fixes
1. ~~Langsmith / langchain don't seem to be implemented yet. I made a research plan and it successfully called the LLM but I never saw the trace show up in my langsmith~~
   **FIXED 2026-06-01 (Phase 6, Step 0):** Root cause was two-fold: (a) `load_dotenv()` was only called in `conftest.py`, never in the worker runtime, so `LANGCHAIN_API_KEY` was never in the environment at startup; (b) `config.py` never read or exported the API key, so the LangChain SDK had no key and silently no-op'd tracing. Fix: `load_dotenv()` added to `main.py` before any worker import; `config.py` now reads `LANGCHAIN_API_KEY` (fallback `LANGSMITH_API_KEY`), exports both env-var names, sets `LANGSMITH_TRACING`/endpoint vars, and exposes a `LANGSMITH_ACTIVE` flag that `main.py` logs at startup. Live verification requires `LANGCHAIN_API_KEY` set in `.env` / Render — see `deferredwork.md`.


# Major Features to add
1. I want to have a stress test feature where we take a report that's been built and then go try to find disproving evidence. I want to have two modes for this: One where it's entirely the LLM making the decision about what questions to ask and what things to poke holes in, and another where it's me, the user, deciding what questions to ask and what things to poke holes in.
