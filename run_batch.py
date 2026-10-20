"""Run the agent over a file of failed payments.

  python run_batch.py                              -> data/failed_payments.json
  python run_batch.py data/holdout_payments.json

Run it twice on the same file: the second time every payment is skipped,
because each payment can only be acted on once.
Results go to data/audit.db (see app/audit.py).

If some payments hit an error, just run the same command again: payments that
were already handled are skipped, so only the failed ones are retried.
"""
import json
import sys
from collections import Counter

from app import audit
from app.agent import build_graph
from app.schemas import FailedPayment

path = sys.argv[1] if len(sys.argv) > 1 else "data/failed_payments.json"
rows = json.load(open(path))

audit.init_db()
graph = build_graph()

statuses = Counter()
for i, row in enumerate(rows, 1):
    try:
        out = graph.invoke({"payment": FailedPayment(**row)})
        statuses[out["status"]] += 1
    except Exception as e:  # network down, LLM gave up, etc.
        statuses["error"] += 1
        print(f"[{i}/{len(rows)}] ERROR on {row['payment_id']}: {type(e).__name__}")
    if i % 10 == 0 or i == len(rows):
        print(f"[{i}/{len(rows)}] {dict(statuses)}")

print("\nRun result :", dict(statuses))
print("Audit log  :", audit.summary())