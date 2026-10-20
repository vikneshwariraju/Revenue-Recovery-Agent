"""Run from project root:  python -m pytest evals/test_llm_retry.py -v
Fakes the Groq call, so no API key and no internet are needed."""
import json
import os
from types import SimpleNamespace

os.environ.setdefault("GROQ_API_KEY", "test-key")  # only so app.llm can be imported

import httpx
import pytest
from groq import APITimeoutError

from app import llm
from app.schemas import Action, FailedPayment


def make_payment() -> FailedPayment:
    return FailedPayment(
        payment_id="pay_1", customer_id="cust_1", amount_inr=999,
        failure_reason="BANK_TIMEOUT", failure_description="timeout",
    )


def ok_response():
    content = json.dumps({"action": "prompt_retry", "reason": "Temporary bank delay.",
                          "confidence": 0.9, "delay_minutes": 0})
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def timeout_error():
    return APITimeoutError(request=httpx.Request("POST", "https://api.groq.com"))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)  # keep tests instant


def test_retries_after_network_timeouts(monkeypatch):
    calls = {"n": 0}

    def fake_create(**kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise timeout_error()
        return ok_response()

    monkeypatch.setattr(llm._client.chat.completions, "create", fake_create)
    decision = llm.decide(make_payment())
    assert decision.action == Action.PROMPT_RETRY
    assert calls["n"] == 3  # two timeouts, then success


def test_gives_up_after_max_attempts(monkeypatch):
    calls = {"n": 0}

    def always_timeout(**kwargs):
        calls["n"] += 1
        raise timeout_error()

    monkeypatch.setattr(llm._client.chat.completions, "create", always_timeout)
    with pytest.raises(RuntimeError):
        llm.decide(make_payment(), max_attempts=3)
    assert calls["n"] == 3