"""Pydantic models: the agent must return validated JSON, never free text."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Action(str, Enum):
    PROMPT_RETRY = "prompt_retry"              # ask customer to retry (same order)
    SEND_PAYMENT_LINK = "send_payment_link"    # new link, other methods offered
    SEND_REMINDER_LATER = "send_reminder_later"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    STOP = "stop"                              # customer opted out


class FailedPayment(BaseModel):
    payment_id: str
    customer_id: str
    amount_inr: int
    failure_reason: str
    failure_description: str
    retry_count: int = 0
    customer_opted_out: bool = False
    expected_action: Optional[str] = None      # only used by evals


class Decision(BaseModel):
    action: Action
    reason: str = Field(description="One-sentence explanation, goes to audit log")
    confidence: float = Field(ge=0.0, le=1.0)
    delay_minutes: int = Field(default=0, ge=0, le=10080)