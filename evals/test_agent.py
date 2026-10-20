"""Run from project root:  python -m pytest evals/test_agent.py -v
Uses a fake LLM and a temp database: no API key, nothing real is touched."""
import pytest

from app import audit
from app.agent import build_graph
from app.schemas import Action, Decision, FailedPayment


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "agent_test.db")
    audit.init_db(path)
    return path


def make_payment(pid="pay_1", **kw) -> FailedPayment:
    base = dict(
        payment_id=pid, customer_id="cust_1", amount_inr=999,
        failure_reason="BANK_TIMEOUT", failure_description="timeout",
        retry_count=0, customer_opted_out=False,
    )
    base.update(kw)
    return FailedPayment(**base)


class FakeLLM:
    """Always suggests prompt_retry and counts how often it is called."""
    def __init__(self, action=Action.PROMPT_RETRY, confidence=0.9):
        self.calls = 0
        self.action = action
        self.confidence = confidence

    def __call__(self, payment):
        self.calls += 1
        return Decision(action=self.action, reason="fake", confidence=self.confidence)


def test_normal_payment_is_executed_and_logged(db):
    llm = FakeLLM()
    out = build_graph(llm, db).invoke({"payment": make_payment()})
    assert out["status"] == "executed"
    assert out["final_decision"].action == Action.PROMPT_RETRY
    assert out["tool_result"]["tool"] == "prompt_retry"
    assert len(audit.get_log(db_path=db)) == 1


def test_safety_overrides_llm_before_execution(db):
    llm = FakeLLM()  # LLM wrongly suggests retry for a Rs 65,000 payment
    out = build_graph(llm, db).invoke({"payment": make_payment(amount_inr=65000)})
    assert out["final_decision"].action == Action.ESCALATE_TO_HUMAN
    assert out["tool_result"]["tool"] == "escalate_to_human"
    row = audit.get_log(db_path=db)[0]
    assert row["llm_action"] == "prompt_retry"
    assert row["final_action"] == "escalate_to_human"
    assert row["overrides"]


def test_same_payment_is_not_acted_on_twice(db):
    llm = FakeLLM()
    graph = build_graph(llm, db)
    first = graph.invoke({"payment": make_payment()})
    second = graph.invoke({"payment": make_payment()})
    assert first["status"] == "executed"
    assert second["status"] == "duplicate_skipped"
    assert llm.calls == 1                      # LLM not even called the second time
    assert len(audit.get_log(db_path=db)) == 1  # only one decision logged


def test_different_payments_both_execute(db):
    graph = build_graph(FakeLLM(), db)
    a = graph.invoke({"payment": make_payment("pay_a")})
    b = graph.invoke({"payment": make_payment("pay_b")})
    assert a["status"] == b["status"] == "executed"


def test_opted_out_customer_is_never_contacted(db):
    out = build_graph(FakeLLM(), db).invoke({"payment": make_payment(customer_opted_out=True)})
    assert out["final_decision"].action == Action.STOP
    assert out["tool_result"]["tool"] == "stop"


def test_low_confidence_goes_to_human(db):
    out = build_graph(FakeLLM(confidence=0.3), db).invoke({"payment": make_payment()})
    assert out["final_decision"].action == Action.ESCALATE_TO_HUMAN