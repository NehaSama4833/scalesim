"""Slot-limited LLM serving cluster under an HPA. One-second ticks.
A replica has `slots` concurrent requests; a request takes a lognormal service time; one global FIFO queue
(an idealised load balancer). New replicas become ready after `startup` seconds (model load) and are billed
from creation. Scale-down removes the replicas' earliest-free slots immediately (in-flight work on a removed
slot is allowed to finish; it is not killed)."""
import heapq
import math
from collections import deque
from dataclasses import dataclass
import numpy as np
from .hpa import HPA, Behavior


@dataclass
class Cfg:
    slots: int = 8
    service_mean: float = 4.0
    service_cv: float = 0.5
    startup: float = 60.0
    initial: int = 3
    min_replicas: int = 1
    max_replicas: int = 20
    duration: int = 2400
    sync: int = 15
    metric_lag: int = 15            # seconds of delay between a reading and the autoscaler seeing it
    signal: str = "inflight"        # util | inflight | queue | static
    target: float = None            # default per signal
    down_window: float = 300.0
    up_window: float = 0.0
    tol: float = 0.1
    seed: int = 0
    exp_service: bool = False       # exponential service (for the Erlang-C validation test)


def default_target(c):
    return {"util": 0.7, "inflight": 0.7 * c.slots, "queue": 2.0}.get(c.signal, 1.0)


def run(rate_fn, c: Cfg):
    rng = np.random.default_rng(c.seed)
    sig2 = math.log(1 + c.service_cv ** 2); mu = math.log(c.service_mean) - sig2 / 2
    svc = (lambda: rng.exponential(c.service_mean)) if c.exp_service else (lambda: rng.lognormal(mu, math.sqrt(sig2)))
    hpa = HPA(c.min_replicas, c.max_replicas, c.target or default_target(c), c.tol, Behavior(c.up_window, c.down_window))
    free = []                                   # per-slot free times (a heap), ready replicas only
    for _ in range(c.initial * c.slots): heapq.heappush(free, 0.0)
    ready, pending = c.initial, []              # pending: ready times of starting replicas
    queue = deque()                             # arrival times
    waits, hist = [], []                        # hist per second: (busy, queued, ready, starting)
    replica_seconds, spec_hist = 0.0, []
    for t in range(c.duration):
        # replicas finishing startup
        while pending and pending[0] <= t:
            heapq.heappop(pending); ready += 1
            for _ in range(c.slots): heapq.heappush(free, float(t))
        # arrivals during [t, t+1)
        n = rng.poisson(max(0.0, rate_fn(t)))
        for a in np.sort(rng.random(n)): queue.append(t + a)
        # dispatch whatever can start before t+1
        while queue and free and free[0] < t + 1:
            f = heapq.heappop(free); arr = queue.popleft()
            start = max(f, arr)
            waits.append(start - arr); heapq.heappush(free, start + svc())
        busy = sum(1 for f in free if f > t + 1)
        hist.append((busy, len(queue), ready, len(pending)))
        replica_seconds += ready + len(pending)
        spec_hist.append(ready + len(pending))
        # autoscaler
        if c.signal != "static" and t > 0 and t % c.sync == 0:
            hi = max(0, t - c.metric_lag); lo = max(0, hi - c.sync)
            w = hist[lo:hi + 1]
            b = np.mean([x[0] for x in w]); q = np.mean([x[1] for x in w]); r = np.mean([x[2] for x in w]) or 1
            m = {"util": b / (r * c.slots), "inflight": (b + q) / r, "queue": q / r}[c.signal]
            cur = ready + len(pending)
            new = hpa.decide(t, ready, len(pending), m)
            if new > cur:
                for _ in range(new - cur): heapq.heappush(pending, t + c.startup)
            elif new < cur:
                k = cur - new
                while k and pending:            # cancel not-yet-ready replicas first
                    pending.remove(max(pending)); heapq.heapify(pending); k -= 1
                if k:
                    ready -= k
                    for _ in range(k * c.slots):
                        if free: heapq.heappop(free)
    # requests still queued at the end: count their wait so far (a lower bound), not hide them
    waits_all = waits + [c.duration - a for a in queue]
    w = np.array(waits_all) if waits_all else np.zeros(1)
    ev = [d for _, d in hpa.events]
    flips = sum(1 for a, b in zip(ev, ev[1:]) if a * b < 0)
    return dict(n=len(w), mean=float(w.mean()), p50=float(np.quantile(w, .5)), p99=float(np.quantile(w, .99)),
                slo_viol=float(np.mean(w > 5.0)), replica_s=replica_seconds, mean_replicas=replica_seconds / c.duration,
                scale_events=len(ev), reversals=flips, unserved=len(queue), max_replicas_seen=max(spec_hist))
