"""What every harness script shares: where vLLM and MemKV are, their counters,
and starting and stopping vLLM on the DGX Sparks.

Settings come from the environment:
  VLLM_URL        vLLM's address (default http://spark1:8000)
  VLLM_API_KEY    vLLM's API key (default: the contents of ~/.vllm-api-key)
  MEMKV_CONSOLES  MemKV console addresses, comma-separated
                  (default http://spark1:9901,http://spark2:9901)
  SPARK_HOSTS     ssh names of the two DGX Sparks, first one runs vLLM (default spark1 spark2)
  LAUNCH          launch.sh on the first DGX Spark (default ~/dgx-spark-agents/setup/vllm/launch.sh)
  LOG_DIR         where vLLM logs go on the first DGX Spark (default ~/vllm-logs)

vLLM runs in tmux window 0 on the first DGX Spark, so you can watch it.
"""

import os, re, subprocess, time, urllib.request

VLLM_URL = os.environ.get("VLLM_URL", "http://spark1:8000")
API_KEY = os.environ.get("VLLM_API_KEY") or open(os.path.expanduser("~/.vllm-api-key")).read().strip()
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
MEMKV_CONSOLES = os.environ.get("MEMKV_CONSOLES", "http://spark1:9901,http://spark2:9901").split(",")
SPARK_HOSTS = os.environ.get("SPARK_HOSTS", "spark1 spark2").split()
LAUNCH = os.environ.get("LAUNCH", "~/dgx-spark-agents/setup/vllm/launch.sh")
LOG_DIR = os.environ.get("LOG_DIR", "~/vllm-logs")

VLLM_COUNTERS = (
    "prompt_tokens_total", "generation_tokens_total", "prefix_cache_hits_total",
    "external_prefix_cache_hits_total", "time_to_first_token_seconds_sum",
    "time_to_first_token_seconds_count", "request_prefill_time_seconds_sum",
    "request_decode_time_seconds_sum",
)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def ssh(host, cmd, check=True):
    return subprocess.run(["ssh", host, cmd], capture_output=True, text=True,
                          errors="replace", check=check).stdout


def vllm_counters():
    """vLLM's token and timing counters, summed over all label sets."""
    req = urllib.request.Request(f"{VLLM_URL}/metrics", headers=HEADERS)
    out = dict.fromkeys(VLLM_COUNTERS, 0.0)
    for line in urllib.request.urlopen(req, timeout=10).read().decode().splitlines():
        m = re.match(r"^vllm:([a-z_]+)(\{[^}]*\})? ([0-9.e+-]+)$", line)
        if m and m.group(1) in out:
            out[m.group(1)] += float(m.group(3))
    return out


def memkv_read_bytes():
    total = 0.0
    for base in MEMKV_CONSOLES:
        for line in urllib.request.urlopen(f"{base}/v1/metrics", timeout=5).read().decode().splitlines():
            if line.startswith("memkv_read_bytes_total "):
                total += float(line.split()[1])
    return total


def serving():
    try:
        urllib.request.urlopen(urllib.request.Request(f"{VLLM_URL}/v1/models", headers=HEADERS), timeout=5)
        return True
    except Exception:
        return False


def containers():
    return [h for h in SPARK_HOSTS if "vllm_node" in ssh(h, "docker ps --format '{{.Names}}'")]


def stop_vllm():
    ssh(SPARK_HOSTS[0], "tmux send-keys -t 0 C-c")
    deadline = time.time() + 240
    while time.time() < deadline:
        if not serving() and not containers():
            return
        time.sleep(5)
    for h in containers():
        ssh(h, "docker stop vllm_node", check=False)
    if containers():
        raise RuntimeError("vLLM containers still running after stop")


def start_vllm(arm, namespace, name):
    """Start vLLM with MemKV ("memkv", under `namespace`) or without ("nomemkv").

    Checks that the server is fresh and in the intended mode before returning
    the MemKV key prefix (None without MemKV).
    """
    if serving() or containers():
        stop_vllm()
    head = SPARK_HOSTS[0]
    log_file = f"{LOG_DIR}/{name}.log"
    ssh(head, f"mkdir -p {LOG_DIR}; rm -f {log_file}; tmux send-keys -t 0 C-u")
    ssh(head, f"tmux send-keys -t 0 '{LAUNCH} {arm} {namespace} {log_file}' Enter")
    deadline = time.time() + 2700
    while not serving():
        if time.time() > deadline:
            raise RuntimeError(f"vLLM did not come up for {name}")
        tail = ssh(head, f"tail -c 4000 {log_file} 2>/dev/null", check=False)
        if "Engine core initialization failed" in tail:
            raise RuntimeError(f"vLLM failed to start; see {head}:{log_file}")
        time.sleep(10)
    text = ssh(head, f"cat {log_file}")
    prefix = None
    if arm == "memkv":
        m = re.search(r"MemKV key prefix (\w+) from 2 worker ranks", text)
        if not m:
            raise RuntimeError(f"{name}: MemKV did not start")
        prefix = m.group(1)
    elif "MemKVOffloadingSpec" in text:
        raise RuntimeError(f"{name}: MemKV loaded in the run without MemKV")
    if vllm_counters()["prompt_tokens_total"] != 0:
        raise RuntimeError(f"{name}: server is not fresh")
    log("up", name, prefix or "")
    return prefix
