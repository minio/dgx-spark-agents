"""Hermes Agent resumes a long session after a vLLM restart, with and without MemKV.

For each repetition, under a new MemKV namespace:
  1. start vLLM with MemKV, ask Hermes the two day-1 questions, snapshot its state
  2. restart vLLM with MemKV, resume on the third question (network cards sampled)
  3. start vLLM without MemKV, resume from the same snapshot (network cards sampled)
Writes results.jsonl, hermes-*.json, nic-*.jsonl and metrics.jsonl to the
output directory; analyze.py restart <out-dir> summarizes them.

  hermes_restart.py <out-dir> [reps] [first-rep]
"""

import json, os, subprocess, sys, time

import common
import hermes_task

HERE = os.path.dirname(os.path.abspath(__file__))
STAMP = time.strftime("%m%d-%H%M")


def sampled_resume(label, nic_path):
    sampler = subprocess.Popen([sys.executable, os.path.join(HERE, "nic_sampler.py"), nic_path])
    time.sleep(10)
    read0, t0 = common.memkv_read_bytes(), time.time()
    hermes_task.resume(label)
    t1, read1 = time.time(), common.memkv_read_bytes()
    time.sleep(5)
    sampler.terminate()
    return {"window": [t0, t1], "memkv_read_bytes": read1 - read0}


def run(out, reps, first=1):
    os.makedirs(out, exist_ok=True)
    hermes_task.HERE = out
    record = lambda row: open(os.path.join(out, "results.jsonl"), "a").write(json.dumps(row) + "\n")
    poller = subprocess.Popen([sys.executable, os.path.join(HERE, "metrics_poller.py"),
                               os.path.join(out, "metrics.jsonl")])
    try:
        for r in range(first, first + reps):
            namespace = f"hermes-restart-{STAMP}-{r}"
            hermes_task.SNAPSHOT = os.path.join(out, f"snapshot-{r}")
            hermes_task.PREFIX = f"hermes-r{r}"

            prefix = common.start_vllm("memkv", namespace, f"hermes-r{r}-day1")
            common.log("rep", r, "day 1")
            hermes_task.day1()
            common.stop_vllm()

            common.start_vllm("memkv", namespace, f"hermes-r{r}-memkv")
            common.log("rep", r, "resume with MemKV")
            extra = sampled_resume("memkv", os.path.join(out, f"nic-r{r}-memkv.jsonl"))
            record({"rep": r, "arm": "memkv", "namespace": namespace, "prefix": prefix, **extra})
            common.stop_vllm()

            common.start_vllm("nomemkv", "-", f"hermes-r{r}-nomemkv")
            common.log("rep", r, "resume without MemKV")
            extra = sampled_resume("nomemkv", os.path.join(out, f"nic-r{r}-nomemkv.jsonl"))
            record({"rep": r, "arm": "nomemkv", **extra})
            common.stop_vllm()
    finally:
        poller.terminate()


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3, int(sys.argv[3]) if len(sys.argv) > 3 else 1)
