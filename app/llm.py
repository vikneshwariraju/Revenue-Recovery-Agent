"""Thin Groq wrapper: JSON output, Pydantic validation, retry on rate limit.

Setup:  pip install groq pydantic python-dotenv
.env:   GROQ_API_KEY=...   (optional) GROQ_MODEL=...
Check Groq's console for current model names; set GROQ_MODEL if the default is gone.
"""
import json
import os
import time

from dotenv import load_dotenv
from groq import APIConnectionError, APITimeoutError, Groq, RateLimitError
from pydantic import ValidationError

from app.schemas import Decision, FailedPayment

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
_client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=30.0)

SYSTEM_PROMPT = """You are a payment recovery assistant for a merchant.
Given ONE failed payment, choose exactly one action using this policy:

- prompt_retry: ONLY for BANK_TIMEOUT or NETWORK_ERROR (transient; the same method will likely work)
- send_payment_link: for UPI_PENDING_FAILED, UPI_APP_ERROR, CARD_DECLINED.
  A UPI request that expired means the customer never approved it, so a retry will not help; send a fresh link with other payment methods.
- send_reminder_later: INSUFFICIENT_FUNDS; set delay_minutes (e.g. 60 to 1440)
- escalate_to_human: SUSPECTED_FRAUD, or UNKNOWN / unclear reason. Never guess.
- stop: customer_opted_out is true

"reason" must be ONE full sentence explaining why, not just the failure code.
Example reason: "Bank did not respond in time, which is usually temporary, so asking the customer to retry is reasonable."

Return ONLY JSON: {"action": "...", "reason": "...", "confidence": 0.0-1.0, "delay_minutes": 0}"""

def decide(payment: FailedPayment, context: str = "", max_attempts: int = 4) -> Decision:
    user_msg = (
        f"Payment: {payment.model_dump_json(exclude={'expected_action'})}\n"
        f"Reference docs:\n{context or 'none'}"
    )
    for attempt in range(max_attempts):
        try:
            resp = _client.chat.completions.create(
                model=MODEL,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            return Decision(**json.loads(resp.choices[0].message.content))
        except (RateLimitError, APITimeoutError, APIConnectionError):
            time.sleep(2 ** attempt)            # free tier: back off and retry
        except (ValidationError, json.JSONDecodeError):
            continue                            # bad output: try again
    raise RuntimeError("LLM failed to return a valid decision")