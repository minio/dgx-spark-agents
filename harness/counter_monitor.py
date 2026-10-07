"""Append vLLM's prompt-token split and MemKV's bytes read to a jsonl file every 10 s.

  counter_monitor.py <out.jsonl>

prompt: prompt tokens; gpu: served from vLLM's GPU cache; ext: loaded from MemKV.
"""
import json, sys, time
import common

while True:
    try:
        v = common.vllm_counters()
        row = {"t": round(time.time(), 1), "prompt": v["prompt_tokens_total"],
               "gpu": v["prefix_cache_hits_total"], "ext": v["external_prefix_cache_hits_total"],
               "memkv_read": common.memkv_read_bytes()}
        with open(sys.argv[1], "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as exc:
        print("monitor:", exc, flush=True)
    time.sleep(10)
