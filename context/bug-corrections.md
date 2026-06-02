# Bug Fixes
1. On research subtopic jobs, they seem to be failing. Here is the error that I'm getting. 

2. I want a "select all" button when selecting sources for the report

3. ~~LangSmith tracing isn't working~~ — RESOLVED 2026-06-02. Root cause: 403 Forbidden from LangSmith API (bad/rotated key or wrong-workspace key). Code fix: endpoint is now configurable via `config.toml [observability] langchain_endpoint` + `LANGCHAIN_ENDPOINT` env var override; startup `check_langsmith()` probe turns a silent 403 into a loud ERROR line; `flush_traces()` added to shutdown. **User action required:** rotate/replace `LANGCHAIN_API_KEY` in Render env — see `deferredwork.md`.

# Major Features to add
1. I want to have a stress test feature where we take a report that's been built and then go try to find disproving evidence. I want to have two modes for this: One where it's entirely the LLM making the decision about what questions to ask and what things to poke holes in, and another where it's me, the user, deciding what questions to ask and what things to poke holes in.
