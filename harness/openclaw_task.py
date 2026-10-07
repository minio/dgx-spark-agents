"""OpenClaw, sandboxed by OpenShell, learning Apache Iceberg in one long session.

The sandbox (setup/openshell/setup-openclaw.sh) holds OpenClaw, a read-only Iceberg
clone at /data/iceberg, and no network except the vLLM endpoint.

  day1 <dir>          run DAY1 in one session, then save OpenClaw's state to <dir>
  resume <dir> <tag>  restore the state from <dir> and ask TASK2 in the same session

Each run writes openclaw-<tag>.json with wall time, OpenClaw's own run
metadata, and vLLM's counters over the run.
"""

import json, os, shlex, subprocess, sys, time

import common

HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = "openclaw"
SESSION = "iceberg"
STATE = "/sandbox/openclaw-state.tgz"

DAY1 = [
    "The Apache Iceberg source code is at /data/iceberg and is read-only. Read "
    "/data/iceberg/format/spec.md from start to end, in consecutive chunks until you "
    "reach the last line. Then explain how an Iceberg table is laid out: table metadata, "
    "snapshots, manifest lists, manifests and data files, and how a reader finds the data "
    "files it needs for a query. Cite line numbers.",
    "Read /data/iceberg/core/src/main/java/org/apache/iceberg/SnapshotProducer.java in full "
    "and the code it calls to commit. Explain step by step what happens when two writers "
    "commit to the same table at the same time. Cite file and line.",
    "Read /data/iceberg/core/src/main/java/org/apache/iceberg/RemoveSnapshots.java and the "
    "file cleanup classes it uses. Explain how snapshot expiration decides which files are "
    "safe to delete. Cite file and line.",
    "Read /data/iceberg/core/src/main/java/org/apache/iceberg/DeleteFileIndex.java in full. "
    "Explain how a reader finds the delete files that apply to a data file. Cite file and line.",
]

TASK2 = (
    "Based on the spec and code you have read, explain how row-level deletes work: position "
    "deletes, equality deletes and deletion vectors. Which format versions support each, when "
    "does a reader apply them, and what does compaction do with them? Cite the spec sections "
    "and the code."
)


def sh(cmd: str, timeout=1800):
    """Run a shell command inside the OpenClaw sandbox with Node 24 first on PATH."""
    return subprocess.run(
        ["openshell", "sandbox", "exec", "-n", SANDBOX, "--timeout", str(timeout),
         "--workdir", "/sandbox", "--", "bash", "-c",
         "export PATH=/opt/node24/bin:$PATH; " + cmd],
        capture_output=True, text=True, timeout=timeout + 60, stdin=subprocess.DEVNULL,
    )


def ask(prompt: str, tag: str) -> dict:
    before = common.vllm_counters()
    t0 = time.time()
    out = sh(f"openclaw agent --local --session-id {SESSION} --json --message {shlex.quote(prompt)}")
    wall = time.time() - t0
    server = {k: round(v - before[k], 1) for k, v in common.vllm_counters().items()}
    try:
        result = json.loads(out.stdout)
    except ValueError:
        result = {"error": out.stdout[-2000:] + out.stderr[-2000:]}
    text = "".join(p.get("text", "") for p in result.get("payloads", []))
    record = {"tag": tag, "wall_s": round(wall, 1), "returncode": out.returncode,
              "server": server, "meta": result.get("meta"), "answer": text,
              "error": result.get("error")}
    json.dump(record, open(os.path.join(HERE, f"openclaw-{tag}.json"), "w"), indent=1)
    print(json.dumps({k: record[k] for k in ("tag", "wall_s", "returncode", "server")}), flush=True)
    return record


def save_state(local_dir: str) -> None:
    os.makedirs(local_dir, exist_ok=True)
    out = sh(f"tar czf {STATE} -C /sandbox .openclaw")
    if out.returncode:
        raise RuntimeError(out.stderr[-1000:])
    subprocess.run(["openshell", "sandbox", "download", SANDBOX, STATE, local_dir],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)


def restore_state(local_dir: str) -> None:
    subprocess.run(["openshell", "sandbox", "upload", "--no-git-ignore", SANDBOX,
                    os.path.join(local_dir, os.path.basename(STATE)), "/sandbox/"],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    out = sh(f"rm -rf /sandbox/.openclaw && tar xzf {STATE} -C /sandbox")
    if out.returncode:
        raise RuntimeError(out.stderr[-1000:])


def day1(local_dir: str, prefix: str = "day1") -> None:
    sh("rm -rf /sandbox/.openclaw/agents/main/sessions/*")
    for i, prompt in enumerate(DAY1, 1):
        ask(prompt, f"{prefix}-{i}")
    save_state(local_dir)


def resume(local_dir: str, tag: str) -> dict:
    restore_state(local_dir)
    return ask(TASK2, tag)


if __name__ == "__main__":
    if sys.argv[1] == "day1":
        day1(sys.argv[2])
    else:
        resume(sys.argv[2], sys.argv[3])
