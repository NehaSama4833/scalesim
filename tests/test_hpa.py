import math, pytest
from scalesim.hpa import HPA, Behavior, raw_desired

def test_doc_example_double_when_metric_is_twice_target():
    assert raw_desired(4, 0, 200, 100) == 8

def test_halves_when_metric_is_half_target():
    assert raw_desired(8, 0, 50, 100) == 4

def test_tolerance_band_prevents_small_changes():
    assert raw_desired(5, 0, 105, 100) == 5 and raw_desired(5, 0, 95, 100) == 5
    assert raw_desired(5, 0, 111, 100) == 6          # ratio 1.11 > 1.1: ceil(5.55)

def test_unready_pods_damp_scale_up():
    # 4 ready at 2x target + 4 unready: with unready counted as zero, ratio = 1.0 -> hold at 8
    assert raw_desired(4, 4, 200, 100) == 8
    # 4 ready at 3x target + 4 unready: new ratio 1.5 -> ceil(1.5*8)=12
    assert raw_desired(4, 4, 300, 100) == 12
    assert raw_desired(4, 0, 300, 100) == 12 and raw_desired(4, 4, 150, 100) == 8   # hold (tolerance after damping)

def test_unready_pods_do_not_block_scale_down():
    assert raw_desired(8, 2, 40, 100) == math.ceil(0.4 * 8)

def test_scale_up_rate_limit_default_policies():
    h = HPA(1, 100, 1.0)
    # want 100, from 3: max(percent 100% -> 6, pods +4 -> 7) = 7
    assert h.decide(15, 3, 0, 100.0) == 7

def test_scale_up_limit_counts_recent_events():
    h = HPA(1, 100, 1.0)
    assert h.decide(15, 3, 0, 100.0) == 7
    # 5 s later still inside the 15 s period: period start is 3 replicas so the cap stays at 7
    assert h.decide(20, 7, 0, 100.0) == 7
    assert h.decide(31, 7, 0, 100.0) == 14                # new period: 100% of 7

def test_scale_down_stabilization_uses_max_in_window():
    h = HPA(1, 100, 1.0, behavior=Behavior(down_window=60))
    assert h.decide(0, 10, 0, 1.0) == 10                  # desired 10
    for t in (15, 30, 45):
        assert h.decide(t, 10, 0, 0.2) == 10              # desired 2, but window remembers 10
    assert h.decide(75, 10, 0, 0.2) < 10                  # window now only holds low recommendations

def test_no_stabilization_scales_down_at_once():
    h = HPA(1, 100, 1.0, behavior=Behavior(down_window=0))
    assert h.decide(0, 10, 0, 0.2) == 2

def test_min_max_clamp():
    h = HPA(2, 6, 1.0, behavior=Behavior(down_window=0))
    assert h.decide(0, 4, 0, 0.0) == 2
    assert h.decide(15, 4, 0, 50.0) == 6
