"""GPU power on both DGX Sparks while idle and while vLLM recomputes one long prompt.

  power_probe.py <request.json> <out.json>

<request.json> is a chat completions request body, for example one saved by
hermes_fleet.py build. A random marker is put in front of the system prompt so
no cached KV can be reused. nvidia-smi is sampled on both DGX Sparks every 0.25 s.
"""

import json, os, statistics, subprocess, sys, threading, time, uuid

import common
import hermes_fleet


def sampler(host, out, stop):
    proc = subprocess.Popen(
        ["ssh", host, "nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits -lms 250"],
        stdout=subprocess.PIPE, text=True)
    for line in proc.stdout:
        out.append((time.time(), float(line.strip())))
        if stop.is_set():
            break
    proc.terminate()


def main(request_path, out_path):
    body = json.load(open(request_path))
    msgs = body["messages"]
    msgs[0] = dict(msgs[0], content=f"[{uuid.uuid4()}]\n" + msgs[0]["content"])
    samples = {h: [] for h in common.SPARK_HOSTS}
    stop = threading.Event()
    threads = [threading.Thread(target=sampler, args=(h, samples[h], stop), daemon=True) for h in samples]
    for t in threads:
        t.start()
    time.sleep(10)
    t0 = time.time()
    res = hermes_fleet._turn(body)
    t1 = time.time()
    time.sleep(10)
    stop.set()
    for t in threads:
        t.join(timeout=5)
    report = {"ttft_s": res.get("ttft_s"), "prompt_tokens": res.get("prompt_tokens"), "busy_s": round(t1 - t0, 1)}
    for h, rows in samples.items():
        idle = [w for t, w in rows if t < t0]
        busy = [w for t, w in rows if t0 + 1 <= t <= t0 + (res.get("ttft_s") or 0)]
        report[h] = {"idle_w": round(statistics.median(idle), 1), "prefill_w": round(statistics.mean(busy), 1)}
    print(json.dumps(report))
    json.dump(report, open(out_path, "w"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
