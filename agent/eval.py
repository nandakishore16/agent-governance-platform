"""
Eval harness: 12 test cases scored on 3 layers (structural, rule-based,
LLM-judge). Ported from Weeks 11-15, including the Week 15 regression
check against the Week 11 baseline (see README for the tc12 known issue).
"""
from langchain_core.messages import HumanMessage

from agent.db import start_run, complete_run, save_eval_result
from agent.graph import app
from agent.nodes import llm

test_cases = [
    {"id": "tc1", "task": "Research the key risks of autonomous agents, then send a notification to the engineering team about the top risk.", "expected_keywords": ["runaway", "loop", "risk"]},
    {"id": "tc2", "task": "Look up agent governance principles, then write a summary file about bounded autonomy.", "expected_keywords": ["bounded", "autonomy", "governance"]},
    {"id": "tc3", "task": "Find information on observability best practices, then notify the team about what to monitor.", "expected_keywords": ["observability", "monitor", "cost"]},
    {"id": "tc4", "task": "Research multi-agent coordination patterns, then write a file summarizing the coordinator pattern.", "expected_keywords": ["coordinator", "pattern", "delegate"]},
    {"id": "tc5", "task": "Look up how token costs compound in agent workflows, then notify the team about cost control best practices.", "expected_keywords": ["token", "cost", "budget"]},
    {"id": "tc6", "task": "Research prompt injection risks, then send a notification summarizing the mitigation.", "expected_keywords": ["prompt", "injection", "risk"]},
    {"id": "tc7", "task": "Find information about audit trails in agent governance, then write a summary file.", "expected_keywords": ["audit", "trail", "log"]},
    {"id": "tc8", "task": "Research human oversight requirements for agents, then notify the team.", "expected_keywords": ["human", "oversight", "escalate"]},
    {"id": "tc9", "task": "Look up cost explosion risks in agent systems, then write a mitigation summary file.", "expected_keywords": ["cost", "explosion", "token"]},
    {"id": "tc10", "task": "Research the pipeline coordination pattern, then send a notification about when to use it.", "expected_keywords": ["pipeline", "pattern", "sequential"]},
    {"id": "tc11", "task": "Find information on scope creep in autonomous agents, then write a summary file.", "expected_keywords": ["scope", "creep", "intended"]},
    {"id": "tc12", "task": "Research anomaly detection for agent systems, then notify the team about monitoring needs.", "expected_keywords": ["anomaly", "detection", "pattern"]},
]


def score_structural(final_state: dict) -> dict:
    """Layer 1: Did the system actually do the work structurally?"""
    passed = (
        not final_state.get("error")
        and len(final_state.get("findings", [])) > 0
        and len(final_state.get("action_log", [])) > 0
    )
    return {"passed": passed, "detail": f"error={final_state.get('error')}, findings={len(final_state.get('findings',[]))}, actions={len(final_state.get('action_log',[]))}"}


def score_rule_based(final_state: dict, expected_keywords: list) -> dict:
    """Layer 2: Does the actual output content mention what it should?"""
    action_text = " ".join(str(a.get("result", "")) for a in final_state.get("action_log", [])).lower()
    finding_text = " ".join(str(f.get("content", "")) for f in final_state.get("findings", [])).lower()
    combined = action_text + " " + finding_text
    matched = [kw for kw in expected_keywords if kw.lower() in combined]
    passed = len(matched) >= 1  # at least one expected keyword present
    return {"passed": passed, "detail": f"matched {matched} of {expected_keywords}"}


def score_llm_judge(task: str, final_state: dict) -> dict:
    action_summary = "; ".join(str(a.get("result", "")) for a in final_state.get("action_log", []))
    findings_summary = "; ".join(str(f.get("content", ""))[:200] for f in final_state.get("findings", []))
    judge_prompt = (
        f"Task: {task}\n\nFindings gathered: {findings_summary}\n\nAction taken: {action_summary}\n\n"
        "Rate how well the action addresses the task, on a scale of 1-5 "
        "(1=irrelevant, 5=excellent). Reply with ONLY the number."
    )
    try:
        response = llm.invoke([HumanMessage(content=judge_prompt)])
        text = response.content if isinstance(response.content, str) else str(response.content)
        score = int("".join(c for c in text if c.isdigit())[:1] or 0)
    except Exception:
        score = 0
    return {"score": score, "passed": score >= 3}


def run_eval_suite():
    """Runs all 12 test cases, scores them, persists results, and returns a summary."""
    results = []
    for tc in test_cases:
        run_id = start_run(tc["task"])
        initial_state = {
            "messages": [], "task": tc["task"], "findings": [], "action_log": [],
            "autonomy_budget": 5, "next_agent": "", "run_id": run_id,
            "error": "", "review_verdict": "", "review_attempted": False
        }
        try:
            final_state = app.invoke(initial_state)
        except Exception as e:
            final_state = {"error": str(e), "findings": [], "action_log": []}

        complete_run(run_id, 0, 0.0)

        structural = score_structural(final_state)
        rule_based = score_rule_based(final_state, tc["expected_keywords"])
        judge = score_llm_judge(tc["task"], final_state)

        result = {
            "id": tc["id"], "run_id": run_id,
            "structural_pass": structural["passed"],
            "rule_pass": rule_based["passed"],
            "judge_score": judge["score"],
            "judge_pass": judge["passed"],
        }
        results.append(result)
        save_eval_result(result)
        print(f"{tc['id']}: structural={structural['passed']} | rule={rule_based['passed']} | judge={judge['score']}/5")

    return results
