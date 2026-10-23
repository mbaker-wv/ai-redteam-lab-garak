#!/usr/bin/env python3
"""
Print every attempt garak scored as a hit (attack succeeded) from a report.jsonl,
plus a count of replies that contain a <think> reasoning block.

Usage:  python3 hits.py <report.jsonl>            show the hits (attacks that worked)
        python3 hits.py <report.jsonl> --empty    show the blank replies (scored as passes)
        add --full to print the whole prompt instead of the last 400 characters
        add --probe NAME to show only one probe, e.g. --probe LatentInjectionResume
No dependencies beyond the standard library.
"""

import json
import sys


def text_of(obj) -> str:
    """garak's prompt/output shapes vary by version; flatten whatever we get to text."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        if "text" in obj:
            return text_of(obj["text"])
        if "turns" in obj:
            return " | ".join(text_of(t.get("content", t)) for t in obj["turns"])
        if "content" in obj:
            return text_of(obj["content"])
    if isinstance(obj, list):
        return " | ".join(text_of(x) for x in obj)
    return str(obj)


def main():
    argv = sys.argv[1:]
    probe_filter = None
    if "--probe" in argv:
        i = argv.index("--probe")
        if i + 1 >= len(argv):
            sys.exit("--probe needs a name, e.g. --probe LatentInjectionResume")
        probe_filter = argv[i + 1]
        del argv[i:i + 2]
    show_empty = "--empty" in argv
    full = "--full" in argv
    args = [a for a in argv if a not in ("--empty", "--full")]
    if len(args) != 1:
        sys.exit("Usage: python3 hits.py <report.jsonl> [--empty] [--full] [--probe NAME]")
    report = args[0]
    empties = 0

    attempts = hits = think = 0
    try:
        with open(report, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # status 2 = attempt has been through the detectors
                if rec.get("entry_type") != "attempt" or rec.get("status") != 2:
                    continue
                if probe_filter and probe_filter not in (rec.get("probe_classname") or ""):
                    continue
                attempts += 1
                outputs = rec.get("outputs") or []
                if any("<think>" in text_of(o) for o in outputs):
                    think += 1
                scores = rec.get("detector_results") or {}
                is_hit = any(s is not None and s >= 0.5
                             for vals in scores.values() for s in (vals or []))
                hits += is_hit
                is_empty = not text_of(outputs).strip()
                empties += is_empty
                if show_empty:
                    if not is_empty:
                        continue
                    print("=" * 80)
                    print(f"PROBE:  {rec.get('probe_classname')}")
                    print(f"PROMPT: {(text_of(rec.get('prompt')) if full else text_of(rec.get('prompt'))[-400:])}")
                    print("REPLY:  (blank)   garak scored this as a PASS")
                    continue
                if not is_hit:
                    continue
                print("=" * 80)
                print(f"PROBE:  {rec.get('probe_classname')}")
                print(f"PROMPT: {(text_of(rec.get('prompt')) if full else text_of(rec.get('prompt'))[-400:])}")
                print(f"REPLY:  {text_of(outputs)[:600]}")
    except FileNotFoundError:
        sys.exit(f"Report not found: {report}")

    print("=" * 80)
    print(f"Evaluated attempts: {attempts}   Hits: {hits}   Blank replies: {empties}   Replies with <think>: {think}")


if __name__ == "__main__":
    main()
