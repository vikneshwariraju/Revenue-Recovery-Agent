"""Generate synthetic failed payments with ground-truth expected actions.

Run:  python data/generate_payments.py
Output: data/failed_payments.json
"""
import json
import random
import sys
import uuid
from pathlib import Path


# failure_reason -> (description, expected_action)
# Actions: prompt_retry | send_payment_link | send_reminder_later | escalate_to_human | stop
FAILURES = {
    "BANK_TIMEOUT": ("Issuing bank did not respond in time", "prompt_retry"),
    "NETWORK_ERROR": ("Network error during authorization", "prompt_retry"),
    "UPI_PENDING_FAILED": ("UPI collect request expired", "send_payment_link"),
    "UPI_APP_ERROR": ("UPI app failed to complete the payment", "send_payment_link"),
    "INSUFFICIENT_FUNDS": ("Customer balance too low", "send_reminder_later"),
    "CARD_DECLINED": ("Card declined by issuer", "send_payment_link"),
    "SUSPECTED_FRAUD": ("Payment flagged as high risk", "escalate_to_human"),
    # Real payments often give a vague reason. Agent must NOT guess here.
    "UNKNOWN": ("Payment failed, reason not specified", "escalate_to_human"),
}

HIGH_AMOUNT_LIMIT = 50000  # rupees; above this a human must approve
MAX_RETRIES = 3


def make_payment() -> dict:
    names = list(FAILURES)
    # weights follow `names` order: timeouts/network/UPI/card common, fraud/unknown rarer
    reason = random.choices(names, weights=[16, 10, 16, 12, 12, 16, 6, 12])[0]
    description, expected = FAILURES[reason]
    amount = random.choice([199, 499, 999, 1499, 2999, 7999, 14999, 24999, 39999, 65000])
    retry_count = random.choice([0, 0, 0, 1, 2, 3])
    opted_out = random.random() < 0.05

    # Safety rules override the default action (priority: opt-out > amount > retries)
    if opted_out:
        expected = "stop"
    elif amount > HIGH_AMOUNT_LIMIT:
        expected = "escalate_to_human"
    elif retry_count >= MAX_RETRIES and expected == "prompt_retry":
        expected = "send_payment_link"

    return {
        "payment_id": f"pay_{uuid.uuid4().hex[:12]}",
        "customer_id": f"cust_{random.randint(1000, 1999)}",
        "amount_inr": amount,
        "failure_reason": reason,
        "failure_description": description,
        "retry_count": retry_count,
        "customer_opted_out": opted_out,
        "expected_action": expected,
    }


def main(n: int = 120, seed: int = 42, out_name: str = "failed_payments.json") -> None:
    random.seed(seed)  # seed set here so each run can use a different one
    payments = [make_payment() for _ in range(n)]
    out = Path(__file__).parent / out_name
    out.write_text(json.dumps(payments, indent=2))
    print(f"Wrote {n} payments to {out}")
    counts = {}
    for p in payments:
        counts[p["expected_action"]] = counts.get(p["expected_action"], 0) + 1
    print("Expected action distribution:", counts)


if __name__ == "__main__":
    args = sys.argv[1:]
    main(
        int(args[0]) if len(args) > 0 else 120,
        int(args[1]) if len(args) > 1 else 42,
        args[2] if len(args) > 2 else "failed_payments.json",
    )