"""
LangGraph assembly — final structure after Week 9 (reviewer added, fan-out
pattern) and Week 13 (timed nodes). This is the version eval'd in Week 15.
"""
from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes import (
    coordinator_node, researcher_node, research_tool_node, capture_findings_node,
    doer_node, action_tool_node, capture_action_node, reviewer_node,
    route_from_coordinator, research_needs_tool, doer_needs_tool,
)


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("coordinator", coordinator_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("research_tool", research_tool_node)
    graph.add_node("capture_findings", capture_findings_node)
    graph.add_node("doer", doer_node)
    graph.add_node("action_tool", action_tool_node)
    graph.add_node("capture_action", capture_action_node)
    graph.add_node("reviewer", reviewer_node)
    graph.set_entry_point("coordinator")
    graph.add_conditional_edges("coordinator", route_from_coordinator,
        {"researcher": "researcher", "doer": "doer", "reviewer": "reviewer", "end": END})
    graph.add_conditional_edges("researcher", research_needs_tool, {"tool": "research_tool", "no_tool": "coordinator"})
    graph.add_edge("research_tool", "capture_findings")
    graph.add_edge("capture_findings", "coordinator")
    graph.add_conditional_edges("doer", doer_needs_tool, {"tool": "action_tool", "no_tool": "coordinator"})
    graph.add_edge("action_tool", "capture_action")
    graph.add_edge("capture_action", "coordinator")
    graph.add_edge("reviewer", "coordinator")
    return graph.compile()


app = build_graph()
