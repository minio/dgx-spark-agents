"""OpenClaw resumes a long session after a vLLM restart, with and without MemKV.

For each repetition, under a new MemKV namespace:
  1. start vLLM with MemKV, ask OpenClaw's four day-1 questions, save its state
  2. restart vLLM with MemKV, restore the state, ask the follow-up (network cards sampled)
  3. start vLLM without MemKV, restore the same state, ask it again (network cards sampled)
vLLM's counters are read every half second throughout (metrics_poller.py).
Writes results.jsonl, openclaw-*.json, nic-*.jsonl and metrics.jsonl to the
output directory; analyze.py restart <out-dir> summarizes them.

  openclaw_restart.py <out-dir> [reps] [first-rep]
"""

import json, os, subprocess, sys, time

import common
import openclaw_task

HERE = os.path.dirname(os.path.abspath(__file__))
STAMP = time.strftime("%m%d-%H%M")


def sampled_resume(state_dir, tag, nic_path):
    sampler = subprocess.Popen([sys.executable, os.path.join(HERE, "nic_sampler.py"), nic_path])
    time.sleep(10)
    openclaw_task.restore_state(state_dir)
    read0, t0 = common.memkv_read_bytes(), time.time()
    openclaw_task.ask(openclaw_task.TASK2, tag)
    t1, read1 = time.time(), common.memkv_read_bytes()
    time.sleep(5)
    sampler.terminate()
    return {"window": [t0, t1], "memkv_read_bytes": read1 - read0}


def run(out, reps, first):
    os.makedirs(out, exist_ok=True)
    openclaw_task.HERE = out
    results = os.path.join(out, "results.jsonl")
    record = lambda row: open(results, "a").write(json.dumps(row) + "\n")
    poller = subprocess.Popen([sys.executable, os.path.join(HERE, "metrics_poller.py"),
                               os.path.join(out, "metrics.jsonl")])
    try:
        for r in range(first, first + reps):
            namespace = f"oc-restart-{STAMP}-{r}"
            state = os.path.join(out, f"state-{r}")
            openclaw_task.SESSION = f"iceberg-{STAMP}-{r}"

            prefix = common.start_vllm("memkv", namespace, f"oc-restart-r{r}-day1")
            common.log("rep", r, "day 1")
            openclaw_task.day1(state, f"r{r}-day1")
            common.stop_vllm()

            common.start_vllm("memkv", namespace, f"oc-restart-r{r}-memkv")
            common.log("rep", r, "resume with MemKV")
            extra = sampled_resume(state, f"r{r}-memkv", os.path.join(out, f"nic-r{r}-memkv.jsonl"))
            record({"rep": r, "arm": "memkv", "namespace": namespace, "prefix": prefix, **extra})
            common.stop_vllm()

            common.start_vllm("nomemkv", "-", f"oc-restart-r{r}-nomemkv")
            common.log("rep", r, "resume without MemKV")
            extra = sampled_resume(state, f"r{r}-nomemkv", os.path.join(out, f"nic-r{r}-nomemkv.jsonl"))
            record({"rep": r, "arm": "nomemkv", **extra})
            common.stop_vllm()
    finally:
        poller.terminate()


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3, int(sys.argv[3]) if len(sys.argv) > 3 else 1)
