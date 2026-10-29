import math
import numpy as np
from scalesim.sim import Cfg, run
from scalesim.scenarios import step

def erlang_c_wait(lam, mu, c):
    a = lam / mu; rho = a / c
    s = sum(a ** k / math.factorial(k) for k in range(c))
    top = a ** c / math.factorial(c) / (1 - rho)
    return top / (s + top) / (c * mu - lam)            # mean waiting time in queue (M/M/c)

def test_static_cluster_matches_erlang_c():
    """With exponential service and a fixed cluster, the simulated mean queueing delay must match the
    M/M/c closed form (24 servers = 3 replicas x 8 slots, mean service 4 s)."""
    for lam, tol in ((5.4, 0.25), (5.7, 0.25)):         # utilisation 0.90 and 0.95
        theory = erlang_c_wait(lam, 1 / 4.0, 24)
        sims = [run(lambda t: lam, Cfg(signal="static", initial=3, exp_service=True, duration=30000, seed=s))["mean"]
                for s in range(4)]
        sim_mean = float(np.mean(sims))
        assert abs(sim_mean - theory) / theory < tol, (lam, theory, sim_mean)

def test_light_load_waits_are_near_zero():
    r = run(lambda t: 2.0, Cfg(signal="static", initial=3, duration=1200, seed=0))
    assert r["p99"] < 0.5 and r["slo_viol"] == 0

def test_overload_static_cluster_grows_a_backlog():
    r = run(lambda t: 20.0, Cfg(signal="static", initial=2, duration=600, seed=0))   # capacity 4 req/s
    assert r["unserved"] > 5000 and r["slo_viol"] > 0.9

def test_replica_seconds_accounting_for_static_cluster():
    r = run(lambda t: 1.0, Cfg(signal="static", initial=3, duration=500, seed=0))
    assert r["replica_s"] == 3 * 500

def test_same_seed_is_reproducible_and_seeds_differ():
    a = run(step, Cfg(duration=900, seed=3)); b = run(step, Cfg(duration=900, seed=3)); c = run(step, Cfg(duration=900, seed=4))
    assert a == b and a != c

def test_autoscaler_scales_up_under_step_load_and_respects_startup():
    r = run(step, Cfg(duration=1500, seed=0, startup=60))
    assert r["max_replicas_seen"] > 3
    fast = run(step, Cfg(duration=1500, seed=0, startup=5))
    slow = run(step, Cfg(duration=1500, seed=0, startup=240))
    assert slow["p99"] > fast["p99"]                     # slower startup must hurt the tail
