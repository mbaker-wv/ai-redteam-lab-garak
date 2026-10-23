#!/usr/bin/env python3
"""
Summarize one or more garak report.jsonl files into a findings table
(attempts, hits, attack success rate, 95% Wilson interval) per probe.
Use it to build the Results table and to compare raw vs agent, or model vs model.

Usage:
    python3 summarize.py raw_qwen3-8b=runs/raw_qwen3-8b.report.jsonl agent_qwen3-8b=runs/agent_qwen3-8b.report.jsonl
    python3 summarize.py ~/.local/share/garak/garak_runs/*.report.jsonl --csv results.csv

Each argument is either LABEL=PATH or just PATH (label = file name).
Standard library only.
"""

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def wilson(hits: int, n: int, z: float = 1.96):
    """95% Wilson score interval. Behaves better than +/- at small n or rates near 0."""
    if n == 0:
        return 0.0, 0.0
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def summarize(path: Path):
    """Return {probe: [attempts, hits, empty_replies]} for evaluated attempts in one report."""
    counts = defaultdict(lambda: [0, 0, 0])
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("entry_type") != "attempt" or rec.get("status") != 2:
                continue
            probe = rec.get("probe_classname", "unknown")
            scores = rec.get("detector_results") or {}
            hit = any(s is not None and s >= 0.5
                      for vals in scores.values() for s in (vals or []))
            outputs = rec.get("outputs") or []
            text = " ".join((o.get("text") or "") if isinstance(o, dict) else str(o or "") for o in outputs)
            counts[probe][0] += 1
            counts[probe][1] += int(hit)
            counts[probe][2] += int(not text.strip())
    return counts


def main():
    ap = argparse.ArgumentParser(description="Summarize garak reports into a findings table")
    ap.add_argument("reports", nargs="+", help="LABEL=PATH or PATH to a .report.jsonl")
    ap.add_argument("--csv", help="Also write rows to this CSV file")
    ap.add_argument("--markdown", action="store_true", help="Print a Markdown table for the paper instead")
    args = ap.parse_args()

    rows = []
    warnings = []
    for item in args.reports:
        label, _, p = item.rpartition("=")
        path = Path(p).expanduser()
        label = label or path.name.replace(".report.jsonl", "")
        if not path.is_file():
            print(f"skipping, not found: {path}", file=sys.stderr)
            continue
        counts = summarize(path)
        if not counts:
            print(f"skipping, no evaluated attempts: {path}", file=sys.stderr)
            continue
        tot_n = tot_h = tot_e = 0
        for probe in sorted(counts):
            n, h, e = counts[probe]
            tot_n += n
            tot_h += h
            tot_e += e
            lo, hi = wilson(h, n)
            rows.append([label, probe, n, h, e, h / n * 100, lo * 100, hi * 100])
        lo, hi = wilson(tot_h, tot_n)
        rows.append([label, "ALL PROBES", tot_n, tot_h, tot_e, tot_h / tot_n * 100, lo * 100, hi * 100])
        if tot_e / tot_n > 0.05:
            msg = f"WARNING: {label} has {tot_e}/{tot_n} empty replies. Pass rate is not trustworthy."
            warnings.append(msg)
            if args.markdown:
                print(msg, file=sys.stderr)

    if not rows:
        sys.exit("No usable reports.")

    header = ["Run", "Probe", "Attempts", "Hits", "Empty", "ASR %", "95% CI low", "95% CI high"]

    if args.markdown:
        # Markdown table, for pasting into the paper
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))
        for r in rows:
            print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]:.2f} | {r[6]:.2f} | {r[7]:.2f} |")
    else:
        # Aligned table for reading in the terminal, one block per run
        cols = ["Probe", "Attempts", "Hits", "Empty", "Attack success", "95% CI (margin of error)"]
        table = []
        for r in rows:
            probe = r[1].split(".", 1)[-1] if r[1] != "ALL PROBES" else "ALL PROBES"
            table.append([r[0], probe, str(r[2]), str(r[3]), str(r[4]),
                          f"{r[5]:.1f}%", f"{r[6]:.1f}% to {r[7]:.1f}%"])
        widths = [max(len(c), *(len(t[i + 1]) for t in table)) for i, c in enumerate(cols)]
        right = {1, 2, 3, 4}
        def line(vals):
            return "  ".join(v.rjust(w) if i in right else v.ljust(w)
                             for i, (v, w) in enumerate(zip(vals, widths)))
        current = None
        for t in table:
            if t[0] != current:
                current = t[0]
                print(f"\n{current}")
                print(line(cols))
                print("  ".join("-" * w for w in widths))
            if t[1] == "ALL PROBES":
                print("  ".join("-" * w for w in widths))
            print(line(t[1:]))
        print()
        for w in warnings:
            print(w)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows([r[:5] + [round(x, 2) for x in r[5:]] for r in rows])
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()
