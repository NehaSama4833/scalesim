import argparse, itertools, json, time
import numpy as np
from .sim import Cfg, run
from .scenarios import SCENARIOS, LONG

KEYS = ["p50", "p99", "slo_viol", "mean_replicas", "scale_events", "reversals", "unserved", "max_replicas_seen"]


def avg(rs):
    return {k: float(np.mean([r[k] for r in rs])) for k in KEYS} | {"p99_range": [min(r["p99"] for r in rs), max(r["p99"] for r in rs)]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", default="results/experiment.json")
    a = ap.parse_args(argv)
    t0 = time.time(); out = {"seeds": a.seeds, "auto": [], "static": []}
    for sc, fn in SCENARIOS.items():
        for n in (4, 6, 10):
            rs = [run(fn, Cfg(signal="static", initial=n, seed=s)) for s in range(a.seeds)]
            out["static"].append(dict(scenario=sc, replicas=n, **avg(rs)))
        for sig, st, dw in itertools.product(["util", "inflight", "queue"], [10, 30, 60, 120, 240], [0, 300]):
            rs = [run(fn, Cfg(signal=sig, startup=st, down_window=dw, seed=s)) for s in range(a.seeds)]
            out["auto"].append(dict(scenario=sc, signal=sig, startup=st, down_window=dw, **avg(rs)))
        print(sc, "done %.0fs" % (time.time() - t0), flush=True)
    out["long"] = []
    for sc, (fn, dur) in LONG.items():
        for n in (4, 6, 10):
            out["long"].append(dict(scenario=sc, signal="static", replicas=n, **avg([run(fn, Cfg(signal="static", initial=n, duration=dur, seed=s)) for s in range(a.seeds)])))
        for sig, st in itertools.product(["util", "inflight"], [30, 120]):
            rs = [run(fn, Cfg(signal=sig, startup=st, down_window=300, duration=dur, seed=s)) for s in range(a.seeds)]
            out["long"].append(dict(scenario=sc, signal=sig, startup=st, down_window=300, **avg(rs)))
        print(sc, "done %.0fs" % (time.time() - t0), flush=True)
    json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
