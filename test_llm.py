import json
from app.schemas import FailedPayment
from app.llm import decide

p = json.load(open("data/failed_payments.json"))[0]
d = decide(FailedPayment(**p))
print("expected:", p["expected_action"])
print("agent   :", d)