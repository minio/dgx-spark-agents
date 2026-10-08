"""Cost per million prompt tokens on two DGX Sparks, and the same tokens priced on APIs.

  cost.py [data-dir]   (default: ../data)

DGX Spark cost per token comes from the 40-session OpenClaw run: hardware and
power per hour, divided by the prompt tokens served per hour in the two
returning rounds of each arm. A "task" is the median resume in the OpenClaw
restart test with MemKV, measured by vLLM's counters.
"""

import json, os, statistics, sys

DGX_SPARK_PRICE = 4699          # NVIDIA list price, USD, each
YEARS = 3
POWER_W = 240                   # each DGX Spark's power supply rating, used as a ceiling
ELECTRICITY = 0.17              # USD per kWh

# USD per million tokens: input, cache read, cache write, output. Standard tier,
# prompts under 200,000 tokens, checked 2026-10-07 at
# claude.com/pricing, developers.openai.com/api/docs/pricing and
# ai.google.dev/gemini-api/docs/pricing. Gemini's cache storage fee per hour
# is not included; Gemini 3.8 Flash's prices double on 2027-01-01.
APIS = {
    "Gemini 3.8 Flash": (0.75, 0.075, 0.75, 3.75),
    "GPT-6.1-Sol": (2.00, 0.10, 2.50, 10.00),
    "Claude Sonnet 5.5": (2.00, 0.10, 2.50, 10.00),
    "Gemini 3.1 Pro": (2.00, 0.20, 2.00, 12.00),
    "Claude Opus 5.5": (4.00, 0.20, 5.00, 20.00),
    "GPT-6-Astra": (10.00, 1.00, 12.50, 50.00),
}


POWER_PER_HOUR = 2 * POWER_W / 1000 * ELECTRICITY


def cost_per_working_hour(hours_per_day):
    """Hardware spread over the hours the DGX Sparks work, plus power while they work."""
    return 2 * DGX_SPARK_PRICE / (YEARS * 365 * hours_per_day) + POWER_PER_HOUR


def fleet_tokens_per_hour(d, arm):
    windows = [json.loads(l) for l in open(os.path.join(d, "openclaw-fleet", "ocfleet-windows.jsonl"))]
    mon = [json.loads(l) for l in open(os.path.join(d, "openclaw-fleet", f"ocfleet-counters-{arm}.jsonl"))]
    at = lambda t: ([m for m in mon if m["t"] <= t] or mon[:1])[-1]
    tokens = seconds = 0.0
    for w in windows:
        if w["label"].startswith(arm + "-r"):
            tokens += at(w["end"] + 10)["prompt"] - at(w["start"])["prompt"]
            seconds += w["end"] - w["start"]
    return tokens / seconds * 3600


def task(d):
    rows = []
    for line in open(os.path.join(d, "openclaw-restart", "results.jsonl")):
        e = json.loads(line)
        if e["arm"] == "memkv":
            s = json.load(open(os.path.join(d, "openclaw-restart", f"openclaw-r{e['rep']}-memkv.json")))["server"]
            computed = s["prompt_tokens_total"] - s["prefix_cache_hits_total"] - s["external_prefix_cache_hits_total"]
            rows.append((s["prompt_tokens_total"], computed, s["generation_tokens_total"]))
    rows.sort()
    return rows[len(rows) // 2]


def main(d):
    prompt, computed, output = task(d)
    per_task_m = prompt / 1e6
    print(f"median task: {prompt:,.0f} prompt tokens, {computed:,.0f} computed, {output:,.0f} written\n")

    print("DGX Sparks                         $/M prompt   $/task")
    for arm in ("memkv", "nomemkv"):
        tph = fleet_tokens_per_hour(d, arm)
        for label, h in (("around the clock", 24), ("8 hours a day", 8)):
            per_m = cost_per_working_hour(h) / (tph / 1e6)
            print(f"  {arm:8s} {label:17s} {tph / 1e6:5.1f} M/h  {per_m:8.4f}   {per_m * per_task_m:7.4f}")

    print("\nAPI (cache hit / cache expired)     $/M prompt          $/task")
    tph = fleet_tokens_per_hour(d, "memkv")
    power_task = POWER_PER_HOUR / tph * prompt
    for name, (inp, read, write, out) in APIS.items():
        hit = ((prompt - computed) * read + computed * write + output * out) / 1e6
        expired = (prompt * inp + output * out) / 1e6
        breakeven = 2 * DGX_SPARK_PRICE / (hit - power_task)
        print(f"  {name:18s} {hit / per_task_m:6.3f} / {expired / per_task_m:6.2f}   {hit:6.3f} / {expired:5.2f}"
              f"   break-even {breakeven:,.0f} tasks, {breakeven * prompt / 1e9:.1f} B tokens,"
              f" {breakeven * prompt / tph:,.0f} h")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
