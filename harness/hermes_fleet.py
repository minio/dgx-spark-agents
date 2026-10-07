"""A fleet of 40 Hermes Agent sessions learning Apache Iceberg, replayed with and without MemKV.

  build          run 40 Hermes sessions, 4 at a time, each in its own Hermes home
                 behind a logging proxy, read-only in bubblewrap. Each session
                 asks five questions about one Iceberg topic; the requests that
                 open questions 3, 4 and 5 are saved as that session's rounds.
  run <label>    replay round 1 for all sessions, then round 2, then round 3,
                 4 at a time, asking for 16 tokens; one JSON line per turn
  ab-same        the same, but every round resends round 1 unchanged
  ab             start vLLM with MemKV (new namespace) and run; start
                 without MemKV and run
"""

import glob, json, os, re, shutil, socket, sqlite3, subprocess, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

import common
from topics import TOPICS, questions

HERE = os.path.dirname(os.path.abspath(__file__))
FLEET = os.path.join(HERE, "hermes-fleet")
CLONE = os.path.join(HERE, "task-hermes-iceberg")  # hermes_task.py day1 creates it
HERMES = os.path.expanduser("~/.hermes")
WORKERS = 4
ROUNDS = 3

def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_home(home, port):
    os.makedirs(home, exist_ok=True)
    cfg = open(os.path.join(HERMES, "config.yaml")).read()
    cfg = re.sub(r"base_url: .*", f'base_url: "http://127.0.0.1:{port}/v1"', cfg, count=1)
    open(os.path.join(home, "config.yaml"), "w").write(cfg)
    shutil.copy2(os.path.join(HERMES, ".env"), os.path.join(home, ".env"))


def _hermes(home, tmp, prompt, resume):
    cmd = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
           "--bind", home, home, "--bind", tmp, tmp, "--setenv", "TMPDIR", tmp,
           "--setenv", "HERMES_HOME", home, "--die-with-parent", "--",
           "hermes", "-z", prompt, "-t", "file", "--in", CLONE]
    if resume:
        cmd += ["--resume", resume]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=5400)


def _opening_request(log_dir, before, prompt):
    """The first logged request after `before` whose last message is this question."""
    for path in sorted(glob.glob(os.path.join(log_dir, "*.json"))):
        if path in before:
            continue
        body = json.load(open(path))
        msgs = body.get("messages") or []
        last = msgs[-1] if msgs else {}
        content = last.get("content")
        text = content if isinstance(content, str) else json.dumps(content)
        if last.get("role") == "user" and prompt[:80] in text and body.get("tools"):
            return body
    return None


def _session(i, worker):
    topic, path = TOPICS[i]
    out = os.path.join(FLEET, f"session-{i:02d}")
    if all(os.path.exists(os.path.join(out, f"round{r}.json")) for r in range(1, ROUNDS + 1)):
        return
    home = os.path.join(FLEET, f"home-{worker}")
    tmp = os.path.join(FLEET, f"tmp-{worker}")
    log_dir = os.path.join(FLEET, f"proxy-{worker}")
    os.makedirs(out, exist_ok=True)
    session = None
    for q, prompt in enumerate(questions(topic, path), 1):
        before = set(glob.glob(os.path.join(log_dir, "*.json")))
        t = time.time()
        res = _hermes(home, tmp, prompt, session)
        if res.returncode != 0:
            raise RuntimeError(f"session {i} question {q}: {res.stderr[-500:]}")
        if session is None:
            db = sqlite3.connect(os.path.join(home, "state.db"))
            session = db.execute("select id from sessions order by started_at desc limit 1").fetchone()[0]
        if q >= 3:
            body = _opening_request(log_dir, before, prompt)
            if body is None:
                raise RuntimeError(f"session {i} question {q}: opening request not found")
            json.dump(body, open(os.path.join(out, f"round{q - 2}.json"), "w"))
        open(os.path.join(out, f"answer{q}.txt"), "w").write(res.stdout)
        print(f"{time.strftime('%H:%M:%S')} session {i:02d} ({topic}) q{q} {time.time() - t:.0f}s", flush=True)


def build():
    os.makedirs(FLEET, exist_ok=True)
    queue = list(range(len(TOPICS)))
    lock = threading.Lock()

    def worker(w):
        port = _free_port()
        home = os.path.join(FLEET, f"home-{w}")
        os.makedirs(os.path.join(FLEET, f"tmp-{w}"), exist_ok=True)
        _make_home(home, port)
        proxy = subprocess.Popen([sys.executable, os.path.join(HERE, "proxy.py"), str(port),
                                  os.path.join(FLEET, f"proxy-{w}")])
        time.sleep(1)
        try:
            while True:
                with lock:
                    if not queue:
                        return
                    i = queue.pop(0)
                # A fresh home per session keeps the session store small and unambiguous.
                for f in glob.glob(os.path.join(home, "state.db*")):
                    os.remove(f)
                _session(i, w)
        finally:
            proxy.terminate()

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(worker, range(WORKERS)))


def _turn(body):
    body = dict(body, max_tokens=16, stream=True, stream_options={"include_usage": True})
    body.pop("max_completion_tokens", None)
    data = json.dumps(body).encode()
    for attempt in (1, 2, 3):
        try:
            req = urllib.request.Request(f"{common.VLLM_URL}/v1/chat/completions", data=data,
                                         headers={**common.HEADERS, "Content-Type": "application/json"})
            t0 = time.time()
            ttft, usage = None, {}
            with urllib.request.urlopen(req, timeout=1800) as r:
                for line in r:
                    if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
                        continue
                    chunk = json.loads(line[6:])
                    if ttft is None and any(c.get("delta") for c in chunk.get("choices", [])):
                        ttft = time.time() - t0
                    usage = chunk.get("usage") or usage
            return {"attempt": attempt, "ttft_s": round(ttft or time.time() - t0, 2),
                    "prompt_tokens": usage.get("prompt_tokens")}
        except Exception as exc:
            err = repr(exc)[:200]
    return {"attempt": 3, "error": err}


def run(label, same=False):
    sessions = sorted(glob.glob(os.path.join(FLEET, "session-*")))
    out = os.path.join(HERE, f"hfleet-{label}.jsonl")
    lock = threading.Lock()
    t0 = time.time()
    open(os.path.join(HERE, f"hfleet-{label}.t0"), "w").write(str(t0))

    def one(r, s):
        body = json.load(open(os.path.join(s, "round1.json" if same else f"round{r}.json")))
        t = time.time()
        row = {"round": r, "agent": os.path.basename(s), "start_s": round(t - t0, 1), **_turn(body)}
        row["wall_s"] = round(time.time() - t, 2)
        with lock, open(out, "a") as f:
            f.write(json.dumps(row) + "\n")

    for r in range(1, ROUNDS + 1):
        with ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(lambda s: one(r, s), sessions))


def ab(same=False):
    stamp = time.strftime("%m%d-%H%M")
    tag = "same-" if same else ""
    for arm, salt in (("memkv", f"hfleet-{tag}{stamp}"), ("nomemkv", "-")):
        common.start_vllm(arm, salt, f"hfleet-{tag}{arm}")
        monitor = subprocess.Popen([sys.executable, os.path.join(HERE, "counter_monitor.py"),
                                    os.path.join(HERE, f"hfleet-counters-{tag}{arm}.jsonl")])
        try:
            run(f"{tag}{arm}", same)
        finally:
            monitor.terminate()
        common.stop_vllm()


if __name__ == "__main__":
    {"build": build, "run": lambda: run(sys.argv[2]), "ab": ab, "ab-same": lambda: ab(True)}[sys.argv[1]]()
