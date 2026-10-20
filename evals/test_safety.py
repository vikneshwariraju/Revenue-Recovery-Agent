"""Run from project root:  pytest evals/test_safety.py -v
These tests need no API key: safety.py is plain Python."""
from app.safety import apply_safety
from app.schemas import Action, Decision, FailedPayment


def make_payment(**kw) -> FailedPayment:
    base = dict(
        payment_id="pay_1", customer_id="cust_1", amount_inr=999,
        failure_reason="BANK_TIMEOUT", failure_description="timeout",
        retry_count=0, customer_opted_out=False,
    )
    base.update(kw)
    return FailedPayment(**base)


def make_decision(action=Action.PROMPT_RETRY, confidence=0.9, delay=0) -> Decision:
    return Decision(action=action, reason="test", confidence=confidence, delay_minutes=delay)


def test_opt_out_always_stops():
    final, ov = apply_safety(make_payment(customer_opted_out=True), make_decision())
    assert final.action == Action.STOP and ov


def test_high_amount_escalates():
    final, ov = apply_safety(make_payment(amount_inr=65000), make_decision())
    assert final.action == Action.ESCALATE_TO_HUMAN and ov


def test_amount_at_limit_is_allowed():
    final, ov = apply_safety(make_payment(amount_inr=50000), make_decision())
    assert final.action == Action.PROMPT_RETRY and not ov


def test_unknown_reason_escalates():
    final, _ = apply_safety(make_payment(failure_reason="UNKNOWN"), make_decision())
    assert final.action == Action.ESCALATE_TO_HUMAN


def test_low_confidence_escalates():
    final, _ = apply_safety(make_payment(), make_decision(confidence=0.4))
    assert final.action == Action.ESCALATE_TO_HUMAN


def test_retry_limit_switches_to_link():
    final, _ = apply_safety(make_payment(retry_count=3), make_decision())
    assert final.action == Action.SEND_PAYMENT_LINK


def test_retry_below_limit_unchanged():
    final, ov = apply_safety(make_payment(retry_count=2), make_decision())
    assert final.action == Action.PROMPT_RETRY and not ov


def test_opt_out_beats_high_amount():
    p = make_payment(customer_opted_out=True, amount_inr=120000)
    final, _ = apply_safety(p, make_decision())
    assert final.action == Action.STOP


def test_good_decision_passes_untouched():
    d = make_decision(Action.SEND_REMINDER_LATER, 0.95, 60)
    final, ov = apply_safety(make_payment(failure_reason="INSUFFICIENT_FUNDS"), d)
    assert final == d and not ov

def test_unrecognised_reason_escalates():
    final, _ = apply_safety(make_payment(failure_reason="PROCESSING_ERROR"), make_decision())
    assert final.action == Action.ESCALATE_TO_HUMAN