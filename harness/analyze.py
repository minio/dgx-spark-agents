"""Summarize the measurements in data/ (or your own runs).

  analyze.py restart <dir>        one row per repetition and arm, then medians and ranges
  analyze.py openclaw-fleet <dir> per round: prompt tokens, where they came from, time
  analyze.py hermes-fleet <dir>   per round: wait for the first word, where the prompt came from
"""

import glob, json, os, statistics, sys
from collections import defaultdict


def nic_burst(path, t0, t1):
    """First stretch of RDMA traffic after t0: seconds and GB received over all rails."""
    series = defaultdict(list)
    for line in open(path):
        r = json.loads(line)
        if t0 - 2 <= r["t"] <= t1:
            series[(r["host"], r["iface"])].append(r)
    total = defaultdict(float)
    for rows in series.values():
        for a, b in zip(rows, rows[1:]):
            total[round(b["t"] - t0)] += b["rx"] - a["rx"]
    secs = sorted(total)
    active = [t for t in secs if total[t] > 1.0e9]
    if not active:
        return 0, 0.0
    start, end, quiet = active[0], active[0], 0
    for t in secs:
        if t < start:
            continue
        if total[t] > 1.0e9:
            end, quiet = t, 0
        else:
            quiet += 1
            if quiet >= 2:
                break
    return end - start + 1, sum(total[t] for t in range(start, end + 1)) / 1e9


def first_request(metrics, t0, t1):
    """Wait for the first word and the prompt split of the first request after t0."""
    rows = [r for r in metrics if t0 - 1 <= r["t"] <= t1 + 5]
    if not rows or rows[0]["t"] > t0 + 2:
        return {}
    base = rows[0]
    a = next((r for r in rows if r["time_to_first_token_seconds_count"] - base["time_to_first_token_seconds_count"] >= 1), None)
    if not a:
        return {}
    d = lambda k: a[k] - base[k]
    return {"first_word_s": round(d("time_to_first_token_seconds_sum"), 1),
            "session_tokens": int(d("prompt_tokens_total")),
            "restored_tokens": int(d("external_prefix_cache_hits_total"))}


def restart(d):
    metrics = [json.loads(l) for l in open(os.path.join(d, "metrics.jsonl"))]
    agent = "openclaw" if glob.glob(os.path.join(d, "openclaw-*.json")) else "hermes"
    rows = []
    for line in open(os.path.join(d, "results.jsonl")):
        e = json.loads(line)
        s = json.load(open(os.path.join(d, f"{agent}-r{e['rep']}-{e['arm']}.json")))["server"]
        secs, gb = nic_burst(os.path.join(d, f"nic-r{e['rep']}-{e['arm']}.jsonl"), *e["window"])
        rows.append({
            "rep": e["rep"], "arm": e["arm"], **first_request(metrics, *e["window"]),
            "computed_tokens": int(s["prompt_tokens_total"] - s["prefix_cache_hits_total"] - s["external_prefix_cache_hits_total"]),
            "prompt_tokens": int(s["prompt_tokens_total"]),
            "prefill_s": round(s["request_prefill_time_seconds_sum"], 1),
            "memkv_read_gb": round(e["memkv_read_bytes"] / 1e9, 3),
            "nic_burst_s": secs, "nic_burst_gb": round(gb, 1),
        })
    for r in rows:
        print(json.dumps(r))
    for arm in ("memkv", "nomemkv"):
        a = [r for r in rows if r["arm"] == arm]
        print(f"\n{arm} (n={len(a)})")
        keys = dict.fromkeys(k for r in a for k in r if k not in ("rep", "arm"))
        for k in keys:
            v = [r[k] for r in a if k in r]
            print(f"  {k:16s} median {round(statistics.median(v), 3):>12}   range {min(v)} to {max(v)}   (n={len(v)})")


def _at(mon, t):
    before = [m for m in mon if m["t"] <= t]
    return before[-1] if before else mon[0]


def openclaw_fleet(d):
    windows = [json.loads(l) for l in open(os.path.join(d, "ocfleet-windows.jsonl"))]
    turns = [json.loads(l) for l in open(os.path.join(d, "ocfleet-turns.jsonl"))]
    built = {t["session"]: t["prompt_tokens"] for t in turns if t["label"] == "build-q2" and t.get("prompt_tokens")}
    print(json.dumps({"sessions": len(built), "session_tokens_after_build": sum(built.values())}))
    for w in windows:
        arm = "build" if w["label"].startswith("build") else w["label"].rsplit("-", 1)[0]
        mon = [json.loads(l) for l in open(os.path.join(d, f"ocfleet-counters-{arm}.jsonl"))]
        a, b = _at(mon, w["start"]), _at(mon, w["end"] + 10)
        prompt, gpu, ext = (b[k] - a[k] for k in ("prompt", "gpu", "ext"))
        hours = (w["end"] - w["start"]) / 3600
        rt = [t for t in turns if t["label"] == w["label"]]
        print(json.dumps({
            "round": w["label"], "turns": len(rt), "failed": sum(not t["ok"] for t in rt),
            "hours": round(hours, 2), "prompt_mtok": round(prompt / 1e6, 2),
            "computed_mtok": round((prompt - gpu - ext) / 1e6, 2),
            "from_gpu_cache": f"{gpu / prompt:.0%}", "from_memkv": f"{ext / prompt:.0%}",
            "prompt_mtok_per_hour": round(prompt / 1e6 / hours, 1),
        }))


def hermes_fleet(d):
    for turns_path in sorted(glob.glob(os.path.join(d, "hfleet-*.jsonl"))):
        label = os.path.basename(turns_path)[len("hfleet-"):-len(".jsonl")]
        if label.startswith("counters"):
            continue
        t0 = float(open(os.path.join(d, f"hfleet-{label}.t0")).read())
        mon = [json.loads(l) for l in open(os.path.join(d, f"hfleet-counters-{label}.jsonl"))]
        rows = [json.loads(l) for l in open(turns_path)]
        for r in sorted({x["round"] for x in rows}):
            rr = [x for x in rows if x["round"] == r and "error" not in x]
            start = min(x["start_s"] for x in rr)
            end = max(x["start_s"] + x["wall_s"] for x in rr)
            a, b = _at(mon, t0 + start), _at(mon, t0 + end + 10)
            prompt, gpu, ext = (b[k] - a[k] for k in ("prompt", "gpu", "ext"))
            print(json.dumps({
                "run": label, "round": r, "turns": len(rr), "minutes": round((end - start) / 60, 1),
                "first_word_median_s": round(statistics.median(x["ttft_s"] for x in rr), 1),
                "from_gpu_cache": f"{gpu / prompt:.0%}", "from_memkv": f"{ext / prompt:.0%}",
                "computed": f"{(prompt - gpu - ext) / prompt:.0%}",
            }))


if __name__ == "__main__":
    {"restart": restart, "openclaw-fleet": openclaw_fleet, "hermes-fleet": hermes_fleet}[sys.argv[1]](sys.argv[2])
