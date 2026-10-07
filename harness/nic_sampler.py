"""Sample RDMA byte counters on both rails of both DGX Sparks once a second.

  nic_sampler.py <out.jsonl>    append {"t", "host", "iface", "rx", "tx"} rows until killed
  nic_sampler.py report <out.jsonl> [t0 t1]
                                per-rail and total GB moved and peak GB/s
"""

import json, os, signal, subprocess, sys, threading, time
from collections import defaultdict

HOSTS = tuple(os.environ.get("SPARK_HOSTS", "spark1 spark2").split())
IFACES = ("enp1s0f0np0", "enP2p1s0f0np0")
REMOTE = (
    "while :; do t=$(date +%s.%N); for i in " + " ".join(IFACES) + "; do "
    "ethtool -S $i | awk -v t=$t -v i=$i "
    "'/rx_vport_rdma_unicast_bytes/{rx=$2} /tx_vport_rdma_unicast_bytes/{tx=$2} "
    "END{printf \"%s %s %s %s\\n\", t, i, rx, tx}' || exit; done; sleep 1; done"
)


def sample(out):
    lock = threading.Lock()
    procs = []

    def stop(*_):
        for proc in procs:
            proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def follow(host):
        proc = subprocess.Popen(["ssh", host, REMOTE], stdout=subprocess.PIPE, text=True)
        procs.append(proc)
        for line in proc.stdout:
            t, iface, rx, tx = line.split()
            row = {"t": float(t), "host": host, "iface": iface, "rx": int(rx), "tx": int(tx)}
            with lock, open(out, "a") as f:
                f.write(json.dumps(row) + "\n")

    threads = [threading.Thread(target=follow, args=(h,), daemon=True) for h in HOSTS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def report(path, t0=0.0, t1=float("inf")):
    series = defaultdict(list)
    for line in open(path):
        r = json.loads(line)
        if t0 <= r["t"] <= t1:
            series[(r["host"], r["iface"])].append(r)
    total = {"rx": 0, "tx": 0}
    for key, rows in sorted(series.items()):
        moved = {d: rows[-1][d] - rows[0][d] for d in ("rx", "tx")}
        peak = {
            d: max(((b[d] - a[d]) / (b["t"] - a["t"]) for a, b in zip(rows, rows[1:])), default=0)
            for d in ("rx", "tx")
        }
        for d in total:
            total[d] += moved[d]
        print(
            f"{key[0]} {key[1]:14s} rx {moved['rx'] / 1e9:7.2f} GB (peak {peak['rx'] / 1e9:5.2f} GB/s)  "
            f"tx {moved['tx'] / 1e9:7.2f} GB (peak {peak['tx'] / 1e9:5.2f} GB/s)"
        )
    print(f"all rails: rx {total['rx'] / 1e9:.2f} GB, tx {total['tx'] / 1e9:.2f} GB")


if __name__ == "__main__":
    if sys.argv[1] == "report":
        report(sys.argv[2], *map(float, sys.argv[3:5]))
    else:
        sample(sys.argv[1])
