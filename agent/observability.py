"""Optional, execution-time Langfuse instrumentation."""
from contextlib import contextmanager

@contextmanager
def observation(name, kind="span", input_data=None):
    # Import lazily: SQLite-only runs do not require Langfuse credentials.
    from agent.tracing import get_langfuse
    client = get_langfuse()
    if client is None:
        yield None
        return
    with client.start_as_current_observation(as_type=kind, name=name, input=input_data) as span:
        yield span
