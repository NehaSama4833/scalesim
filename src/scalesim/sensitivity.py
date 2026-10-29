"""How much do conclusions depend on the two timing constants I assumed (metric delay, HPA sync period)?
Step scenario, startup 60 s, scale-down window 300 s, 3 seeds."""
import numpy as np
from .sim import Cfg, run
from .scenarios import step

def main():
    print("signal   lag sync | p99 wait | SLO viol | mean replicas | max replicas")
    for sig in ("util", "inflight"):
        for lag, sync in ((0, 15), (15, 15), (30, 15), (15, 5), (15, 30)):
            rs = [run(step, Cfg(signal=sig, startup=60, down_window=300, metric_lag=lag, sync=sync, seed=s)) for s in range(3)]
            print("%-8s %3d %4d | %8.1f | %8.3f | %13.1f | %.0f" % (sig, lag, sync, np.mean([r["p99"] for r in rs]),
                  np.mean([r["slo_viol"] for r in rs]), np.mean([r["mean_replicas"] for r in rs]), np.mean([r["max_replicas_seen"] for r in rs])))

if __name__ == "__main__":
    main()
