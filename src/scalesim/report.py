import json, sys

def main(p):
    d = json.load(open(p)); A = d["auto"]
    print("seeds per cell:", d["seeds"], "| wait = queueing delay before a request starts (TTFT proxy); SLO = wait > 5 s")
    print("\nSTATIC baselines (scenario, replicas): p99 wait s | SLO violation | mean replicas")
    for s in d["static"]:
        print("  %-6s n=%-2d  p99 %7.1f | viol %.3f | replicas %.1f" % (s["scenario"], s["replicas"], s["p99"], s["slo_viol"], s["mean_replicas"]))
    for sc in dict.fromkeys(a["scenario"] for a in A):
        print("\n== %s: p99 wait (s) / SLO violation / mean replicas / reversals  [rows: signal+down_window, cols: startup s]" % sc)
        sts = sorted({a["startup"] for a in A})
        print("%-16s" % "" + "".join("%-30s" % ("startup %d" % s) for s in sts))
        for sig in ("util", "inflight", "queue"):
            for dw in (0, 300):
                row = "%-16s" % ("%s dw=%d" % (sig, dw))
                for st in sts:
                    a = next(x for x in A if x["scenario"] == sc and x["signal"] == sig and x["startup"] == st and x["down_window"] == dw)
                    row += "%-30s" % ("%6.1f/%.3f/%.1f/%.1f" % (a["p99"], a["slo_viol"], a["mean_replicas"], a["reversals"]))
                print(row)

    print("\n== RARE PEAK (3 h run, 20-minute plateau): p99 wait / SLO violation / mean replicas (max replicas seen)")
    for x in d.get("long", []):
        tag = "static n=%d" % x["replicas"] if x["signal"] == "static" else "%s startup=%d dw=300" % (x["signal"], x["startup"])
        print("  %-26s p99 %7.1f | viol %.3f | replicas %5.2f (max %.0f)" % (tag, x["p99"], x["slo_viol"], x["mean_replicas"], x["max_replicas_seen"]))

if __name__ == "__main__":
    main(sys.argv[1])
