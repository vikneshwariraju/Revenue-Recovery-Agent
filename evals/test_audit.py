"""Run from project root:  python -m pytest evals/test_audit.py -v
Uses a temporary database, so your real data/audit.db is untouched."""
import pytest

from app import audit
from app.schemas import Action, Decision, FailedPayment


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test_audit.db")
    audit.init_db(path)
    return path


def make_payment(pid="pay_1") -> FailedPayment:
    return FailedPayment(
        payment_id=pid, customer_id="cust_1", amount_inr=999,
        failure_reason="BANK_TIMEOUT", failure_description="timeout",
    )


def make_decision(action=Action.PROMPT_RETRY) -> Decision:
    return Decision(action=action, reason="test reason", confidence=0.9, delay_minutes=0)


def test_claim_action_only_first_time(db):
    assert audit.claim_action("pay_1", "send_payment_link", db) is True
    assert audit.claim_action("pay_1", "send_payment_link", db) is False


def test_claim_is_per_payment(db):
    assert audit.claim_action("pay_1", "prompt_retry", db) is True
    assert audit.claim_action("pay_2", "prompt_retry", db) is True


def test_log_and_read_back(db):
    llm = make_decision(Action.PROMPT_RETRY)
    final = make_decision(Action.SEND_PAYMENT_LINK)
    audit.log_decision(make_payment(), llm, final, ["retry_count>=3 -> send_payment_link"], db)
    rows = audit.get_log(db_path=db)
    assert len(rows) == 1
    assert rows[0]["llm_action"] == "prompt_retry"
    assert rows[0]["final_action"] == "send_payment_link"
    assert rows[0]["overrides"] == ["retry_count>=3 -> send_payment_link"]


def test_summary_counts(db):
    audit.log_decision(make_payment("a"), make_decision(), make_decision(), [], db)
    audit.log_decision(make_payment("b"), make_decision(Action.PROMPT_RETRY),
                       make_decision(Action.ESCALATE_TO_HUMAN), ["amount>50000 -> escalate_to_human"], db)
    s = audit.summary(db)
    assert s["total"] == 2
    assert s["overridden_by_safety"] == 1
    assert s["by_action"]["escalate_to_human"] == 1


def test_init_db_is_safe_to_run_twice(db):
    audit.init_db(db)
    audit.init_db(db)
    assert audit.summary(db)["total"] == 0