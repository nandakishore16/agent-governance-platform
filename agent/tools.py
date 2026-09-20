"""Agent tools: one read-only retrieval tool, two state-changing action stubs."""
from langchain_core.tools import tool

from agent.rag import collection


@tool
def retrieve_governance_knowledge(query: str) -> str:
    """Search the governance knowledge base for information on agent governance,
    risks, observability, coordination patterns, or cost management."""
    results = collection.query(query_texts=[query], n_results=2)
    docs = results["documents"][0]
    return "\n\n---\n\n".join(docs) if docs else "No relevant documents found."


@tool
def write_file_stub(filename: str, content: str) -> str:
    """Write content to a file. This is a state-changing action."""
    return f"[would write {len(content)} chars to {filename}]"


@tool
def send_notification_stub(recipient: str, message: str) -> str:
    """Send a notification to a recipient. This is a state-changing action."""
    return f"[would notify {recipient}: {message}]"


research_tools = [retrieve_governance_knowledge]
action_tools = [write_file_stub, send_notification_stub]
