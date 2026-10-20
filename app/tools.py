"""Action tools. Right now they only SIMULATE (no money, no messages sent).

Later, only this file changes: e.g. send_payment_link will call Razorpay's
Payment Links API in test mode. The agent code does not need to change.
"""
from typing import Callable, Dict

from app.schemas import Action, Decision, FailedPayment


def _simulated(tool: str, payment: FailedPayment, detail: str) -> dict:
    return {
        "status": "simulated",
        "tool": tool,
        "payment_id": payment.payment_id,
        "customer_id": payment.customer_id,
        "detail": detail,
    }


def prompt_retry(payment: FailedPayment, decision: Decision) -> dict:
    return _simulated("prompt_retry", payment, "asked customer to retry the same order")


def send_payment_link(payment: FailedPayment, decision: Decision) -> dict:
    return _simulated("send_payment_link", payment,
                      f"sent a fresh payment link for Rs {payment.amount_inr}")


def send_reminder_later(payment: FailedPayment, decision: Decision) -> dict:
    return _simulated("send_reminder_later", payment,
                      f"scheduled a reminder in {decision.delay_minutes} minutes")


def escalate_to_human(payment: FailedPayment, decision: Decision) -> dict:
    return _simulated("escalate_to_human", payment, "added to the human review queue")


def stop(payment: FailedPayment, decision: Decision) -> dict:
    return _simulated("stop", payment, "no contact: customer opted out")


TOOLS: Dict[Action, Callable[[FailedPayment, Decision], dict]] = {
    Action.PROMPT_RETRY: prompt_retry,
    Action.SEND_PAYMENT_LINK: send_payment_link,
    Action.SEND_REMINDER_LATER: send_reminder_later,
    Action.ESCALATE_TO_HUMAN: escalate_to_human,
    Action.STOP: stop,
}