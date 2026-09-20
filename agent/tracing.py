"""Langfuse tracing wrapper around a single agent run (Week 10)."""
import sqlite3
import os

from agent.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST, DB_PATH
from agent.db import start_run, complete_run
from agent.nodes import OUTPUT_COST_PER_M
from agent.graph import app

_langfuse_client = None


def get_langfuse():
    """Lazily create the Langfuse client so the app can still run (without
    tracing) if Langfuse keys aren't configured."""
    global _langfuse_client
    if _langfuse_client is None:
        if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
            return None
        os.environ["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = LANGFUSE_HOST
        from langfuse import get_client
        _langfuse_client = get_client()
    return _langfuse_client


def run_with_langfuse(task: str, autonomy_budget: int = 5) -> dict:
    langfuse = get_langfuse()
    run_id = start_run(task)
    initial_state = {
        "messages": [], "task": task, "findings": [], "action_log": [],
        "autonomy_budget": autonomy_budget, "next_agent": "", "run_id": run_id,
        "error": "", "review_verdict": "", "review_attempted": False
    }

    if langfuse is None:
        # No tracing configured — still run the graph and log to SQLite.
        final_state = app.invoke(initial_state)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT tokens FROM events WHERE run_id = ?", (run_id,))
        total_tokens = sum(r[0] for r in cursor.fetchall())
        conn.close()
        complete_run(run_id, total_tokens, round((total_tokens / 1_000_000) * OUTPUT_COST_PER_M, 6))
        return final_state

    with langfuse.start_as_current_observation(
        as_type="span", name="agent-governance-run",
        input={"task": task}, metadata={"sqlite_run_id": run_id}
    ) as root_span:

        final_state = app.invoke(initial_state)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT event_type, tool_name, tool_input, tool_output, tokens, duration_ms FROM events WHERE run_id = ?", (run_id,))
        events = cursor.fetchall()
        total_tokens = sum(e[4] for e in events)
        conn.close()

        for event_type, tool_name, tool_input, tool_output, tokens, duration_ms in events:
            with langfuse.start_as_current_observation(
                as_type="span", name=tool_name or event_type,
                input={"input": tool_input}, metadata={"event_type": event_type, "tokens": tokens, "duration_ms": duration_ms}
            ) as child_span:
                child_span.update(output={"output": tool_output})

        root_span.update(output={
            "findings": len(final_state.get("findings", [])),
            "actions": len(final_state.get("action_log", []))
        })

    complete_run(run_id, total_tokens, round((total_tokens / 1_000_000) * OUTPUT_COST_PER_M, 6))
    langfuse.flush()
    return final_state
