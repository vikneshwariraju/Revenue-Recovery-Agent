"""LangGraph flow for one failed payment.

    START -> check_duplicate --(already handled)--> END
                  |
                  v (new payment)
               decide (LLM) -> safety (code) -> execute (tool) -> log -> END

The LLM only suggests. safety.py has the final say, and audit.claim_action()
makes sure the same payment is never acted on twice.
"""
from typing import Callable, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app import audit
from app.safety import apply_safety
from app.schemas import Decision, FailedPayment
from app.tools import TOOLS


class AgentState(TypedDict, total=False):
    payment: FailedPayment
    llm_decision: Decision
    final_decision: Decision
    overrides: List[str]
    status: str          # "executed" | "duplicate_skipped"
    tool_result: dict


def build_graph(decide_fn: Optional[Callable[[FailedPayment], Decision]] = None,
                db_path: str = audit.DEFAULT_DB):
    """decide_fn can be swapped for a fake in tests, so they need no API key."""
    if decide_fn is None:
        from app.llm import decide as decide_fn  # imported lazily: needs GROQ_API_KEY

    def check_duplicate(state: AgentState) -> dict:
        if audit.has_action(state["payment"].payment_id, db_path):
            return {"status": "duplicate_skipped", "tool_result": {}}
        return {}

    def decide_node(state: AgentState) -> dict:
        return {"llm_decision": decide_fn(state["payment"])}

    def safety_node(state: AgentState) -> dict:
        final, overrides = apply_safety(state["payment"], state["llm_decision"])
        return {"final_decision": final, "overrides": overrides}

    def execute_node(state: AgentState) -> dict:
        payment, final = state["payment"], state["final_decision"]
        # claim_action is the real lock: if two runs race, only one gets True
        if not audit.claim_action(payment.payment_id, final.action.value, db_path):
            return {"status": "duplicate_skipped", "tool_result": {}}
        return {"status": "executed", "tool_result": TOOLS[final.action](payment, final)}

    def log_node(state: AgentState) -> dict:
        overrides = list(state["overrides"])
        if state["status"] == "duplicate_skipped":
            overrides.append("duplicate_action_blocked")
        audit.log_decision(state["payment"], state["llm_decision"],
                           state["final_decision"], overrides, db_path)
        return {}

    def route_after_check(state: AgentState) -> str:
        return "skip" if state.get("status") == "duplicate_skipped" else "go"

    g = StateGraph(AgentState)
    g.add_node("check_duplicate", check_duplicate)
    g.add_node("decide", decide_node)
    g.add_node("safety", safety_node)
    g.add_node("execute", execute_node)
    g.add_node("log", log_node)

    g.add_edge(START, "check_duplicate")
    g.add_conditional_edges("check_duplicate", route_after_check,
                            {"skip": END, "go": "decide"})
    g.add_edge("decide", "safety")
    g.add_edge("safety", "execute")
    g.add_edge("execute", "log")
    g.add_edge("log", END)
    return g.compile()