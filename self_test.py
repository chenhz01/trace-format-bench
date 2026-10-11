# -*- coding: utf-8 -*-
"""self_test.py for trace-format-bench.

Three test families (ALIGNMENT-16 rule 97):
  A. functional  -- round-trip, compression, view dedup, CLI
  B. error paths -- bad magic, truncation, bad utf-8, missing file
  C. extreme edge -- empty input, 100k-event superlong input, huge field value

Run:  python self_test.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trace_format_bench as tfb

PASS = 0
FAIL = 0
RESULTS = []


def check(name, cond, info=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    RESULTS.append("%-4s %s %s" % (tag, name, info))


def section(t):
    RESULTS.append("")
    RESULTS.append("== %s ==" % t)


# ---------- A. functional ----------
section("A. functional")
text = tfb._demo_text(500)
events = tfb.parse_log_lines(text)
check("parse yields 500 events", len(events) == 500, "got %d" % len(events))

blob = tfb.pack_events(events)
back = tfb.unpack_events(blob)
check("pack/unpack round-trip identity", back == events)
check("ir smaller than raw text", len(blob) < len(text.encode()),
      "%d vs %d bytes" % (len(blob), len(text.encode())))

view = tfb.analyzer_view(events)
check("view much smaller than raw", len(view) < len(text) * 0.25,
      "%d vs %d chars" % (len(view), len(text)))
check("view dedups repeats", "repeat_counts:" in view and "# templates:" in view)

r = tfb.bench(tfb._demo_text(2000))
check("bench metrics complete",
      all(k in r for k in ("events", "raw_bytes", "ir_bytes",
                           "compression_ratio", "pack_ms", "unpack_ms")))
check("bench ratio > 1 on synthetic log", r["compression_ratio"] > 1.0,
      "ratio=%.3f" % r["compression_ratio"])

# CLI smoke: demo + convert + view pipeline
tmp = tempfile.mkdtemp(prefix="tfb_")
log_path = os.path.join(tmp, "app.log")
tir_path = os.path.join(tmp, "app.tir")
with open(log_path, "w", encoding="utf-8") as f:
    f.write(text)
cli = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "trace_format_bench.py")]
p1 = subprocess.run(cli + ["convert", log_path, tir_path],
                    capture_output=True, text=True)
check("cli convert exit 0", p1.returncode == 0, p1.stdout.strip()[:60])
p2 = subprocess.run(cli + ["view", tir_path, "--min-level", "WARN"],
                    capture_output=True, text=True)
check("cli view exit 0 + filtered", p2.returncode == 0 and "I " not in p2.stdout.split("\n")[0],
      p2.stdout.split("\n")[0][:50])

# ---------- B. error paths ----------
section("B. error paths")
for label, bad in [("bad magic", b"XXXX" + blob[4:]),
                   ("truncated mid-record", blob[:len(blob) // 2]),
                   ("empty blob", b""),
                   ("header-only truncation", blob[:6])]:
    try:
        tfb.unpack_events(bad)
        check("rejects %s" % label, False, "no exception")
    except ValueError as exc:
        check("rejects %s" % label, True, str(exc)[:40])

bad_utf8 = blob[:-3] + b"\xff\xfe\xfd"  # clobber last field value bytes
try:
    tfb.unpack_events(bad_utf8)
    check("rejects corrupt utf-8 field", False, "no exception")
except ValueError:
    check("rejects corrupt utf-8 field", True)

p3 = subprocess.run(cli + ["view", os.path.join(tmp, "missing.tir")],
                    capture_output=True, text=True)
check("cli missing file -> nonzero exit", p3.returncode != 0)

# ---------- C. extreme edge ----------
section("C. extreme edge")
check("empty text -> 0 events", tfb.parse_log_lines("") == [])
eblob = tfb.pack_events([])
check("empty container round-trip", tfb.unpack_events(eblob) == [], "container=%dB" % len(eblob))
check("empty bench survives", tfb.bench("")["events"] == 0)

big_text = tfb._demo_text(100000)
t0 = time.perf_counter()
big_events = tfb.parse_log_lines(big_text)
big_blob = tfb.pack_events(big_events)
big_back = tfb.unpack_events(big_blob)
dt = time.perf_counter() - t0
check("100k events round-trip", big_back == big_events and len(big_back) == 100000,
      "%.2fs" % dt)
check("100k under 10s", dt < 10.0, "%.2fs" % dt)

huge_field = {"blob": "x" * 500000}
hb = tfb.pack_events([{"ts": 1.0, "level": "INFO", "event": "e", "fields": huge_field}])
check("500KB single field round-trip",
      tfb.unpack_events(hb)[0]["fields"]["blob"] == "x" * 500000,
      "ir=%dB" % len(hb))

junk_event = tfb.parse_log_lines("\n\n  \nnot a real log line at all\n")
check("garbage line tolerated", len(junk_event) == 1)

# ---------- report ----------
print("\n".join(RESULTS))
print("")
print("trace-format-bench self-test: %d/%d PASS (families A/B/C)" % (PASS, PASS + FAIL))
bench_line = tfb.bench(tfb._demo_text(2000))
print("bench(2000 events): ratio=%s view=%s%% of raw | repro: python trace_format_bench.py demo"
      % (bench_line["compression_ratio"], bench_line["view_vs_raw_pct"]))
sys.exit(0 if FAIL == 0 else 1)
