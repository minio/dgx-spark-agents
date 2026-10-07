"""Append vLLM's counters to a jsonl file every half second, skipping while vLLM is down.

  metrics_poller.py <out.jsonl>
"""
import json, sys, time
import common

while True:
    try:
        row = {"t": round(time.time(), 2), **common.vllm_counters()}
        with open(sys.argv[1], "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    time.sleep(0.5)
