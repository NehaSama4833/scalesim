import math

def step(t):    return 4.0 if t < 600 or t >= 1500 else 14.0
def ramp(t):    return 9.0 + 7.0 * math.sin(2 * math.pi * t / 1200 - math.pi / 2)
def spike(t):   return 15.0 if 900 <= t < 990 else 5.0

SCENARIOS = {"step": step, "ramp": ramp, "spike": spike}

def rare_peak(t): return 14.0 if 3600 <= t < 4800 else 3.0   # 20-minute plateau in a 3-hour quiet day

LONG = {"rare_peak": (rare_peak, 10800)}
