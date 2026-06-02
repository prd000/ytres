"""
LangSmith startup probe and shutdown flush.

check_langsmith() — called at startup; makes one authenticated API call so that
    a 403/401 becomes a loud ERROR instead of a buried per-job WARNING.
flush_traces()    — called at shutdown; waits for any in-flight trace batches.
"""
import logging

log = logging.getLogger(__name__)


def check_langsmith() -> None:
    from worker.config import LANGSMITH_ACTIVE, LANGCHAIN_PROJECT, LANGCHAIN_ENDPOINT

    if not LANGSMITH_ACTIVE:
        log.warning(
            "LangSmith tracing: INACTIVE — no API key. "
            "Set LANGCHAIN_API_KEY in Render env vars (not .env) to enable tracing."
        )
        return

    import os
    key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY") or ""
    masked = f"…{key[-4:]}" if len(key) >= 4 else "…"

    try:
        import langsmith
        client = langsmith.Client()

        # create_project is idempotent — catch a conflict (project already exists)
        # and treat it as success.  Any other exception bubbles to the outer handler.
        try:
            client.create_project(LANGCHAIN_PROJECT)
        except Exception as inner:
            s = str(inner)
            if (
                "409" in s
                or "conflict" in s.lower()
                or "already exists" in s.lower()
                or type(inner).__name__ == "LangSmithConflictError"
            ):
                pass  # project already exists — auth is fine
            else:
                raise

        log.info(
            "LangSmith OK — project=%s endpoint=%s key=%s",
            LANGCHAIN_PROJECT, LANGCHAIN_ENDPOINT, masked,
        )

    except Exception as exc:
        s = str(exc)
        is_auth = (
            "403" in s
            or "401" in s
            or "Forbidden" in s
            or "Unauthorized" in s
            or type(exc).__name__ in ("LangSmithAuthError", "LangSmithError")
        )
        if is_auth:
            status = "403" if "403" in s else "401" if "401" in s else "auth error"
            log.error(
                "LangSmith auth FAILED (%s) — key revoked/rotated, wrong workspace, or wrong "
                "region (EU keys need LANGCHAIN_ENDPOINT=https://eu.api.smith.langchain.com). "
                "endpoint=%s",
                status, LANGCHAIN_ENDPOINT,
            )
        else:
            log.warning(
                "LangSmith probe failed (non-auth error: %s). endpoint=%s",
                exc, LANGCHAIN_ENDPOINT,
            )


def flush_traces() -> None:
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers
        wait_for_all_tracers()
        log.info("LangSmith traces flushed")
    except Exception as exc:
        log.warning("LangSmith flush failed: %s", exc)
