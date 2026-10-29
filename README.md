# Scalesim

A simulation of the Kubernetes **Horizontal Pod Autoscaler (HPA)** rule driving an LLM-serving deployment, to see how scaling signal, scale-down stabilization and **model start-up time** interact. Replicas have a fixed number of request slots, new replicas take `startup` seconds to become ready (model load), and queueing delay before a request starts stands in for time-to-first-token inflation.

**Status: Day 9 MVP, simulation only.** I had planned a real cluster (kind/k3s); this sandbox cannot pull container images from any registry, and downloading and running a k3s binary as root was blocked by the permission check, so you chose a simulation instead. Nothing here ran on Kubernetes.

## Problem and what exists
The HPA rule is documented and widely explained, and KEDA/Knative offer queue- and concurrency-based scaling. This repo adds no new autoscaler. It is a small, reproducible way to see how the stock rule behaves when a "pod" takes minutes to become useful. It is **not** the predictive LSTM autoscaling project; there is no forecasting here.

## What is implemented
- `hpa.py`: my re-implementation of the documented HPA behaviour: `desired = ceil(ready * metric/target)` with a 10% tolerance; not-ready pods counted as zero usage when scaling up; stabilization windows (scale-down: highest recommendation in the window; scale-up: lowest); rate limits (default scale-up: max of +100% or +4 pods per 15 s; scale-down: -100% per 15 s); min/max replicas. **I could not read the official documentation page through my fetch tool, and I did not compare against the Kubernetes source or a real cluster**, so treat this as "my understanding of the documented rule".
- `sim.py`: 1-second ticks; 8 slots per replica; lognormal service time (mean 4 s, CV 0.5), so one replica serves about 2 req/s; one global FIFO queue (an idealised load balancer); replicas billed from creation; HPA sync every 15 s on metrics that are 15 s old.
- Signals: `util` (busy slots / slots, target 0.7), `inflight` ((busy + queued) per ready replica, target 0.7 x slots), `queue` (queued per ready replica, target 2).
- Scenarios (`scenarios.py`): `step` (4 to 14 req/s for 15 minutes), `ramp` (sinusoid 2..16 req/s), `spike` (5 to 15 req/s for 90 s), each 40 minutes, and `rare_peak` (3 hours, 20-minute plateau at 14 req/s, otherwise 3 req/s).

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q                                          # 16 tests
.venv/bin/python -m scalesim.experiment                       # about 15 s
.venv/bin/python -m scalesim.report results/experiment.json   # tables
.venv/bin/python -m scalesim.sensitivity
```

## Validation
The queueing core is checked against the **Erlang-C closed form** for a fixed cluster with exponential service (24 slots, utilisation 0.90 and 0.95): simulated mean wait 0.856 s vs 0.860 s theory, and 2.39 s vs 2.44 s (tests assert within 25%). HPA arithmetic is tested against the documented examples (double when the metric is twice the target, tolerance band, unready-pod damping, rate limits, stabilization, clamps). There is no check that the HPA matches a real cluster.

## Results (3 seeds per cell; full tables in `results/experiment_table.txt`)
Wait = seconds in queue before a request starts. "Violation" = share of requests that waited more than 5 s. Requests still queued at the end count with their wait so far.

1. **Start-up time dominates the tail.** `ramp`, utilisation signal, 300 s scale-down window: p99 wait is 0.3 s, 1.9 s, 6.7 s, 98.6 s and 405.9 s at start-up times of 10, 30, 60, 120 and 240 s. At 240 s start-up no setting I tried avoided a large violation share on the `step` scenario with the utilisation signal (76-90%).
2. **A 300 s scale-down window removes flapping and costs capacity.** `step`, in-flight signal, 60 s start-up: direction reversals fall from 28 to 4, violations from 0.31 to 0.10, and mean replicas rise from 9.9 to 11.6 (+17%). Without the window every signal reversed direction 15 to 52 times per 40 minutes.
3. **The queue-depth-only signal was the worst here.** With a window it averaged 15 to 18 replicas (more than 10 fixed replicas, which had zero violations) and still violated the 5 s wait for 13 to 58% of requests. A queue of zero says nothing about spare capacity, and a backlog only shows up after users are already waiting.
4. **Utilisation vs in-flight is not a clean win.** In-flight had the better p99 in every `step` cell with the window, and halved violations at 60 s start-up (0.10 vs 0.20 at +26% replicas), but at 120 s start-up the utilisation signal had the lower violation share (0.08 vs 0.17). The utilisation signal saturates at 100%, so it asks for at most 1.43x per sync; in-flight can ask for much more from a backlog. I did not run enough seeds or settings to say which is better in general.
5. **Overshoot.** Autoscaled runs reached 19 to 20 replicas (the cap) in the `step` scenario with 60 s start-up, although the peak needs about 8 to 10. While new replicas are loading, the metric from the ready ones stays high and the controller keeps asking for more. Increasing the metric delay or sync period did not remove it (`results/sensitivity.txt`).
6. **Autoscaling did not always save money.** For the 40-minute scenarios, fixed 10 replicas had zero violations; the best autoscaled setting on `step` (in-flight, 10 s start-up, window) had 4.3% violations at 10.9 mean replicas. Autoscaling paid off in the `rare_peak` run (3 h): 4.5-5.2 mean replicas vs 10 fixed, at 3% to 17% violations (30 s start-up: 3-5%; 120 s: 7-17%).

Sensitivity (`step`, 60 s start-up, window 300 s): changing the metric delay (0/15/30 s) or sync period (5/15/30 s) moved the p99 wait between 26 s and 63 s but kept the in-flight signal's violation share below the utilisation signal's in all ten settings tried.

## Limitations (read these)
- **A simulation, not a cluster.** The HPA code is my reading of the documentation, unverified against Kubernetes.
- **Every number depends on my choices:** 8 slots and a 4 s mean service time, a global queue with perfect load balancing, start-up of 10 to 240 s with no image-pull or scheduling delay, billed from creation, a metric delay and sync period of 15 s, a 5 s violation threshold, traffic shapes picked by me, and a 20-replica cap. None is measured from a real system.
- **No GPU realism:** no CPU/GPU metrics, no batching dynamics inside a replica (a slot is an independent server), no KV-cache memory limit, no cold-start variance, no node provisioning, no pod disruption or draining beyond letting in-flight work on removed slots finish.
- **Three seeds per cell**, ranges are visible only for p99 in the JSON. One cell (`step`, in-flight, window, 240 s start-up) has a lower violation share than its 120 s neighbour (0.064 vs 0.171); I did not investigate it.
- Bursty arrivals are Poisson within each second; request-length variability is a single lognormal.

## Future work
Run the same workload on a real kind/k3s cluster with HPA and a custom-metrics adapter (needs a registry or an offline image path); model GPU batching and KV-cache limits; compare KEDA/Knative rules; pre-warmed pools and predictive scale-up (overlaps your LSTM autoscaling project).
