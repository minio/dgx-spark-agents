"""Hermes Agent learning Apache Iceberg in one long session, across a server restart.

Hermes runs read-only: inside bubblewrap the whole filesystem is mounted
read-only except Hermes's own state directory and an empty temp directory,
the Iceberg clone has no write permission, and Hermes gets only the file
toolset (no terminal). Every task is a question about the code.

ICEBERG_SRC is a local clone of https://github.com/apache/iceberg (we used commit
c24eeea). Each run clones it again into a read-only working copy.

  day1            clone Apache Iceberg, run DAY1 prompts in one Hermes session,
                  then snapshot Hermes's state
  resume <label>  restore that state and resume the session on TASK2

Each run writes hermes-<label>.json with the same server counters as
openclaw_task.py, and checks that the clone is unchanged.
"""

import json, os, shutil, sqlite3, stat, subprocess, sys, time

import common

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.expanduser(os.environ.get("ICEBERG_SRC", "~/iceberg"))
CWD = os.path.join(HERE, "task-hermes-iceberg")
TMP = os.path.join(HERE, "hermes-tmp")
HERMES = os.path.expanduser("~/.hermes")
STATE = ("state.db", "state.db-wal", "state.db-shm", "sessions", "memories", "skills")
SNAPSHOT = os.path.join(HERE, "task-hermes-iceberg-snapshot")
PREFIX = "hermes-iceberg"
TOOLSETS = "file"

DAY1 = [
    "Read format/spec.md in full. Then explain how an Iceberg table is laid out: table "
    "metadata, snapshots, manifest lists, manifests and data files, and how a reader finds "
    "the data files it needs for a query.",
    "Read the Java code that commits a new snapshot, starting from "
    "core/src/main/java/org/apache/iceberg/SnapshotProducer.java and following what it calls. "
    "Explain step by step what happens when two writers commit to the same table at the same "
    "time. Cite file and line.",
]

TASK2 = (
    "Based on the spec and code you have read, explain how row-level deletes work: position "
    "deletes, equality deletes and deletion vectors. Which format versions support each, when "
    "does a reader apply them, and what does compaction do with them? Cite the spec sections "
    "and the code."
)


def _sandboxed(cmd):
    os.makedirs(TMP, exist_ok=True)
    return [
        "bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--bind", HERMES, HERMES, "--bind", TMP, TMP, "--setenv", "TMPDIR", TMP,
        "--die-with-parent", "--", *cmd,
    ]


def _hermes(prompt, label, resume=None):
    cmd = ["hermes", "-z", prompt, "-t", TOOLSETS, "--in", CWD,
           "--usage-file", os.path.join(TMP, f"{PREFIX}-{label}-usage.json")]
    if resume:
        cmd += ["--resume", resume]
    return subprocess.run(_sandboxed(cmd), capture_output=True, text=True, timeout=3600)


def _latest_session():
    db = sqlite3.connect(os.path.join(HERMES, "state.db"))
    return db.execute("select id from sessions order by started_at desc limit 1").fetchone()[0]


def _tree_state():
    return subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=CWD,
                          capture_output=True, text=True).stdout


def _run(label, prompt, resume):
    before = common.vllm_counters()
    t0 = time.time()
    out = _hermes(prompt, label, resume)
    wall = time.time() - t0
    server = {k: round(v - before[k], 1) for k, v in common.vllm_counters().items()}
    record = {
        "label": label,
        "wall_s": round(wall, 1),
        "server": server,
        "clone_unchanged": _tree_state() == "",
        "returncode": out.returncode,
        "answer": out.stdout[-3000:],
        "stderr": out.stderr[-1500:],
    }
    json.dump(record, open(os.path.join(HERE, f"{PREFIX}-{label}.json"), "w"), indent=1)
    print(json.dumps({k: record[k] for k in ("label", "wall_s", "clone_unchanged", "returncode", "server")}), flush=True)


def _make_read_only(root):
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames + dirnames:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                os.chmod(path, os.stat(path).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    os.chmod(root, os.stat(root).st_mode & ~stat.S_IWUSR)


def _remove(path):
    if os.path.isdir(path):
        subprocess.run(["chmod", "-R", "u+w", path], check=True)
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def day1():
    _remove(CWD)
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{REPO}", CWD], check=True)
    _make_read_only(CWD)
    session = None
    for i, prompt in enumerate(DAY1, 1):
        _run(f"day1-{i}", prompt, session)
        session = session or _latest_session()
    _remove(SNAPSHOT)
    os.makedirs(os.path.join(SNAPSHOT, "hermes"))
    for name in STATE:
        src = os.path.join(HERMES, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(SNAPSHOT, "hermes", name))
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(SNAPSHOT, "hermes", name))
    open(os.path.join(SNAPSHOT, "session"), "w").write(session)


def resume(label):
    for name in STATE:
        _remove(os.path.join(HERMES, name))
        src = os.path.join(SNAPSHOT, "hermes", name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(HERMES, name))
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(HERMES, name))
    _run(label, TASK2, open(os.path.join(SNAPSHOT, "session")).read())


if __name__ == "__main__":
    day1() if sys.argv[1] == "day1" else resume(sys.argv[2])
