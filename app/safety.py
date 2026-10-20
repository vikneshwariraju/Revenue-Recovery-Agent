"""Safety layer: plain code that overrides the LLM when a rule is broken.

Principle: the LLM suggests, this code decides. Rules are checked in priority
order and every override is returned so it can go into the audit log.

NOTE: HIGH_AMOUNT_LIMIT and MAX_RETRIES are also used by data/generate_payments.py
to build expected answers. Keep both files in sync.
"""
from typing import List, Tuple

from app.schemas import Action, Decision, FailedPayment

HIGH_AMOUNT_LIMIT = 50_000   # rupees; above this a human must approve
MAX_RETRIES = 3              # after this, stop asking the customer to retry
MIN_CONFIDENCE = 0.6         # below this the agent is not sure enough to act
MAX_DELAY_MINUTES = 7 * 24 * 60
KNOWN_REASONS = {
    "BANK_TIMEOUT", "NETWORK_ERROR", "UPI_PENDING_FAILED", "UPI_APP_ERROR",
    "INSUFFICIENT_FUNDS", "CARD_DECLINED", "SUSPECTED_FRAUD",
}


def apply_safety(payment: FailedPayment, decision: Decision) -> Tuple[Decision, List[str]]:
    """Return (final_decision, list_of_overrides). Highest-priority rule wins."""
    overrides: List[str] = []
    final = decision.model_copy()

    # 1. Customer opted out: never contact them again.
    if payment.customer_opted_out:
        if final.action != Action.STOP:
            overrides.append("customer_opted_out -> stop")
        final.action = Action.STOP
        final.delay_minutes = 0
        return final, overrides

    # 2. High amount: a human must approve.
    if payment.amount_inr > HIGH_AMOUNT_LIMIT:
        if final.action != Action.ESCALATE_TO_HUMAN:
            overrides.append(f"amount>{HIGH_AMOUNT_LIMIT} -> escalate_to_human")
        final.action = Action.ESCALATE_TO_HUMAN
        final.delay_minutes = 0
        return final, overrides

    # 3. Unknown failure reason: do not guess.
    if payment.failure_reason not in KNOWN_REASONS:
        if final.action != Action.ESCALATE_TO_HUMAN:
            overrides.append("unknown_reason -> escalate_to_human")
        final.action = Action.ESCALATE_TO_HUMAN
        final.delay_minutes = 0
        return final, overrides

    # 4. Low confidence: do not act on a shaky decision.
    if final.confidence < MIN_CONFIDENCE and final.action != Action.ESCALATE_TO_HUMAN:
        overrides.append(f"confidence<{MIN_CONFIDENCE} -> escalate_to_human")
        final.action = Action.ESCALATE_TO_HUMAN
        final.delay_minutes = 0
        return final, overrides

    # 5. Too many retries: switch to a fresh payment link instead of retrying.
    if final.action == Action.PROMPT_RETRY and payment.retry_count >= MAX_RETRIES:
        overrides.append(f"retry_count>={MAX_RETRIES} -> send_payment_link")
        final.action = Action.SEND_PAYMENT_LINK
        final.delay_minutes = 0

    # 6. Clamp delay to a sane range.
    clamped = max(0, min(final.delay_minutes, MAX_DELAY_MINUTES))
    if clamped != final.delay_minutes:
        overrides.append(f"delay clamped to {clamped}")
        final.delay_minutes = clamped

    return final, overrides