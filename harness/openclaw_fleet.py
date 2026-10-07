"""40 OpenClaw sessions learning Apache Iceberg on one server, with and without MemKV.

Four OpenShell sandboxes (oc-w0..oc-w3) each run ten sessions in turn, so four
agents are active at once. Each session asks about its own Iceberg topic.

  openclaw_fleet.py <out-dir>

Builds the sessions (two questions each) on vLLM with MemKV and saves every
sandbox's state. Then, once with MemKV and once without, restarts vLLM,
restores the state and runs two rounds in which every session asks its next
real question.

Per turn: start time, wall time, OpenClaw's own prompt size, success.
Per round: GPU / MemKV / computed split from the counter monitor.
"""

import json, os, shlex, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import common
import topics

HERE = os.path.dirname(os.path.abspath(__file__))
WORKERS = 4
SANDBOXES = [f"oc-w{w}" for w in range(WORKERS)]
STATE = "/sandbox/openclaw-state.tgz"
STAMP = time.strftime("%m%d-%H%M")


def questions(topic, path):
    """Two build questions and two round questions per topic, pointing at /data/iceberg."""
    qs = topics.questions(topic, path)
    qs = [q.replace("format/spec.md", "/data/iceberg/format/spec.md")
           .replace(f"read {path}", f"read /data/iceberg/{path}") for q in qs]
    qs[0] = "The Apache Iceberg source code is at /data/iceberg and is read-only. " + qs[0]
    return qs


def sh(sandbox, cmd, timeout=3000):
    return subprocess.run(
        ["openshell", "sandbox", "exec", "-n", sandbox, "--timeout", str(timeout),
         "--workdir", "/sandbox", "--", "bash", "-c", "export PATH=/opt/node24/bin:$PATH; " + cmd],
        capture_output=True, text=True, timeout=timeout + 60, stdin=subprocess.DEVNULL)


def turn(sandbox, session, prompt):
    t = time.time()
    out = sh(sandbox, f"openclaw agent --local --session-id {session} --json --message {shlex.quote(prompt)}")
    try:
        res = json.loads(out.stdout)
    except ValueError:
        res = {"error": (out.stdout + out.stderr)[-500:]}
    meta = (res.get("meta") or {}).get("agentMeta") or {}
    return {"start": round(t, 1), "wall_s": round(time.time() - t, 1),
            "ok": out.returncode == 0 and "error" not in res,
            "prompt_tokens": meta.get("promptTokens"), "turns": meta.get("assistantTurns"),
            "error": res.get("error")}


def assignments():
    return {w: [i for i in range(len(topics.TOPICS)) if i % WORKERS == w] for w in range(WORKERS)}


def run_round(label, q_index, out_path):
    lock = threading.Lock()

    def worker(w):
        for i in assignments()[w]:
            topic, path = topics.TOPICS[i]
            row = {"label": label, "session": i, "worker": w,
                   **turn(SANDBOXES[w], f"s{i:02d}", questions(topic, path)[q_index])}
            with lock, open(out_path, "a") as f:
                f.write(json.dumps(row) + "\n")
            print(json.dumps({k: row[k] for k in ("label", "session", "wall_s", "ok", "prompt_tokens")}), flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(worker, range(WORKERS)))
    return {"label": label, "start": t0, "end": time.time()}


def save_states(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    for sbx in SANDBOXES:
        out = sh(sbx, f"tar czf {STATE} -C /sandbox .openclaw")
        assert out.returncode == 0, out.stderr[-500:]
        d = os.path.join(state_dir, sbx)
        os.makedirs(d, exist_ok=True)
        subprocess.run(["openshell", "sandbox", "download", sbx, STATE, d],
                       check=True, capture_output=True, stdin=subprocess.DEVNULL)


def restore_states(state_dir):
    for sbx in SANDBOXES:
        subprocess.run(["openshell", "sandbox", "upload", "--no-git-ignore", sbx,
                        os.path.join(state_dir, sbx, os.path.basename(STATE)), "/sandbox/"],
                       check=True, capture_output=True, stdin=subprocess.DEVNULL)
        out = sh(sbx, f"rm -rf /sandbox/.openclaw && tar xzf {STATE} -C /sandbox")
        assert out.returncode == 0, out.stderr[-500:]


def monitored(out, arm, fn):
    mon = subprocess.Popen([sys.executable, os.path.join(HERE, "counter_monitor.py"),
                            os.path.join(out, f"ocfleet-counters-{arm}.jsonl")])
    try:
        return fn()
    finally:
        mon.terminate()


def ab(out):
    os.makedirs(out, exist_ok=True)
    namespace = f"ocfleet-{STAMP}"
    state_dir = os.path.join(out, "state")
    turns = os.path.join(out, "ocfleet-turns.jsonl")
    windows = os.path.join(out, "ocfleet-windows.jsonl")
    common.start_vllm("memkv", namespace, "ocfleet-build")
    for q in (0, 1):
        w = monitored(out, "build", lambda: run_round(f"build-q{q + 1}", q, turns))
        open(windows, "a").write(json.dumps(w) + "\n")
    save_states(state_dir)
    for arm, arm_namespace in (("memkv", namespace), ("nomemkv", "-")):
        common.start_vllm(arm, arm_namespace, f"ocfleet-{arm}")
        restore_states(state_dir)
        for q, rnd in ((2, 1), (3, 2)):
            w = monitored(out, arm, lambda: run_round(f"{arm}-r{rnd}", q, turns))
            open(windows, "a").write(json.dumps(w) + "\n")


if __name__ == "__main__":
    ab(sys.argv[1])
