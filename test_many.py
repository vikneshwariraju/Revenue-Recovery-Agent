import json
import sys
import time

from app.schemas import FailedPayment
from app.llm import decide
from app.safety import apply_safety

# Which file to test: python test_many.py [path]
path = sys.argv[1] if len(sys.argv) > 1 else "data/failed_payments.json"
rows = json.load(open(path))
n = len(rows)

llm_ok = final_ok = errors = 0
results = []
start = time.time()

for i, p in enumerate(rows, 1):
    pay = FailedPayment(**p)
    try:
        d = decide(pay)
    except RuntimeError:
        errors += 1
        print(f"[{i}/{n}] ERROR (LLM failed) {p['failure_reason']}")
        continue

    f, overrides = apply_safety(pay, d)
    llm_match = d.action.value == p["expected_action"]
    final_match = f.action.value == p["expected_action"]
    llm_ok += llm_match
    final_ok += final_match

    results.append({**p, "llm_action": d.action.value, "final_action": f.action.value,
                    "overrides": overrides, "reason": d.reason})

    mark = "OK " if final_match else "BAD"
    print(f"[{i}/{n}] {mark} {p['failure_reason']} {p['amount_inr']} r={p['retry_count']} "
          f"| exp={p['expected_action']} llm={d.action.value} final={f.action.value} "
          f"({time.time() - start:.0f}s)")

done = n - errors
print(f"\nFile          : {path}")
print(f"LLM alone     : {llm_ok}/{done} = {llm_ok / done:.0%}")
print(f"LLM + safety  : {final_ok}/{done} = {final_ok / done:.0%}")
print(f"LLM errors    : {errors}")

# Save results next to the input file name, so holdout does not overwrite the 120-set results
out_name = "eval_" + path.replace("\\", "/").split("/")[-1]
json.dump(results, open(f"data/{out_name}", "w"), indent=2)
print(f"Saved results : data/{out_name}")