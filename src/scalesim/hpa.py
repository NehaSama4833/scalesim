"""Re-implementation of the Kubernetes HorizontalPodAutoscaler decision rule as I understand its documented
behaviour (NOT verified against Kubernetes source or a real cluster; see README):
  desired = ceil(ready * metric/target)            if |1 - ratio| > tolerance
  not-ready pods are treated as using 0 when scaling up (damps the jump)
  recommendations are stabilised (scale-down: max over window; scale-up: min over window)
  scale-up/scale-down rate limits via policies (Pods or Percent per period; selectPolicy Max)."""
import math
from dataclasses import dataclass, field


@dataclass
class Behavior:
    up_window: float = 0.0
    down_window: float = 300.0
    up_policies: tuple = (("percent", 100, 15), ("pods", 4, 15))
    down_policies: tuple = (("percent", 100, 15),)


def raw_desired(ready, unready, metric_sum_per_ready_avg, target, tol=0.1):
    """metric_sum_per_ready_avg = average metric over READY pods. Returns desired replica count.
    Follows: ratio from ready pods; if scaling up and there are unready pods, recompute with those
    counted as zero usage and keep the current size if that flips direction or lands inside tolerance."""
    if ready <= 0:
        return ready + unready
    ratio = metric_sum_per_ready_avg / target
    if unready == 0 or ratio <= 1.0:
        return ready if abs(1 - ratio) <= tol else math.ceil(ratio * ready)
    new_ratio = (metric_sum_per_ready_avg * ready / (ready + unready)) / target
    if abs(1 - new_ratio) <= tol or new_ratio < 1.0:
        return ready + unready
    return math.ceil(new_ratio * (ready + unready))


@dataclass
class HPA:
    min_replicas: int = 1
    max_replicas: int = 20
    target: float = 0.7
    tol: float = 0.1
    behavior: Behavior = field(default_factory=Behavior)
    history: list = field(default_factory=list)     # (time, recommendation)
    events: list = field(default_factory=list)      # (time, delta) of applied scale changes

    def _limit(self, now, current, policies, up):
        best = None
        for kind, value, period in policies:
            delta_in_period = sum(d for t, d in self.events if now - t < period)
            start = current - delta_in_period       # replicas at the start of the period
            if kind == "pods":
                lim = start + value if up else start - value
            else:
                lim = math.ceil(start * (1 + value / 100)) if up else math.floor(start * (1 - value / 100))
            best = lim if best is None else (max(best, lim) if up else min(best, lim))   # selectPolicy Max
        return best

    def decide(self, now, ready, unready, metric_avg):
        """Returns the new spec replica count (ready + unready = current)."""
        current = ready + unready
        d = raw_desired(ready, unready, metric_avg, self.target, self.tol)
        d = max(self.min_replicas, min(self.max_replicas, d))
        self.history.append((now, d))
        b = self.behavior
        up_rec = min([r for t, r in self.history if t > now - b.up_window] + [d]) if b.up_window > 0 else d
        down_rec = max([r for t, r in self.history if t > now - b.down_window] + [d]) if b.down_window > 0 else d
        rec = current
        if rec < up_rec: rec = up_rec
        if rec > down_rec: rec = down_rec
        if rec > current:
            rec = min(rec, self._limit(now, current, b.up_policies, True))
        elif rec < current:
            rec = max(rec, self._limit(now, current, b.down_policies, False))
        rec = max(self.min_replicas, min(self.max_replicas, rec))
        if rec != current:
            self.events.append((now, rec - current))
        self.history = [(t, r) for t, r in self.history if t > now - max(b.up_window, b.down_window, 1)]
        return rec
