# -*- coding: utf-8 -*-
"""
trace-format-bench -- Structured logs -> compact binary IR -> AI-ready view.

Benchmarks the "convert, don't re-parse" idea borrowed from debugger design
(a la RAD Debugger's RDI): transform structured trace logs once into a compact
binary intermediate representation (TIR1: string table + zigzag-varint delta
timestamps), then derive cheap analyzer views for LLM consumption. Quantifies
byte savings and end-to-end time vs. raw-text re-read.

Pure stdlib. MIT. v0.1.1
"""
import argparse
import json
import struct
import sys
import time

MAGIC = b"TIR1"
LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "CRITICAL": 4}
LEVEL_NAMES = {v: k for k, v in LEVELS.items()}


def _zigzag(n):
    return (n << 1) ^ (n >> 63) if n < 0 else (n << 1)


def _unzigzag(u):
    return (u >> 1) ^ -(u & 1)


def _put_varint(out, u):
    while True:
        b = u & 0x7F
        u >>= 7
        if u:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def _get_varint(data, pos):
    shift = result = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated varint at offset %d" % pos)
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def parse_log_lines(text):
    """Parse lines like: 2026-01-02T03:04:05Z INFO auth.login user=alice ms=12
    Tolerant: blank lines skipped; bare tokens folded into msg field."""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        ts, level, name, fields = 0.0, "INFO", parts[0] if parts else "?", {}
        body = parts
        if body and "T" in body[0]:
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(body[0].replace("Z", "+00:00")).timestamp()
                body = body[1:]
            except ValueError:
                pass
        if body and body[0].upper() in LEVELS:
            level = body[0].upper()
            body = body[1:]
        if body:
            name = body[0]
            body = body[1:]
        for tok in body:
            if "=" in tok:
                k, _, v = tok.partition("=")
                fields[k] = v
            else:
                fields["msg"] = (fields.get("msg", "") + " " + tok).strip()
        events.append({"ts": ts, "level": level, "event": name, "fields": fields})
    return events


def pack_events(events):
    """Pack events into TIR1: string table + varint delta timestamps."""
    strtab, stridx = [], {}

    def intern(s):
        if s not in stridx:
            stridx[s] = len(strtab)
            strtab.append(s)
        return stridx[s]

    name_ids, field_ids = [], []
    prev_ms = 0
    for e in events:
        name_ids.append(intern(str(e.get("event", "?"))))
        fid = []
        for k, v in (e.get("fields") or {}).items():
            fid.append((intern(str(k)), str(v).encode("utf-8")))
        field_ids.append(fid)
    out = bytearray()
    out += MAGIC
    out += struct.pack("<IH", len(events), len(strtab))
    for s in strtab:
        sb = s.encode("utf-8")
        out += struct.pack("<H", len(sb))
        out += sb
    for i, e in enumerate(events):
        level_id = LEVELS.get(str(e.get("level", "INFO")).upper(), 1)
        out += struct.pack("<B", level_id)
        _put_varint(out, _zigzag(int(round(float(e.get("ts", 0.0)) * 1000)) - prev_ms))
        prev_ms = int(round(float(e.get("ts", 0.0)) * 1000))
        out += struct.pack("<H", name_ids[i])
        out += struct.pack("<H", len(field_ids[i]))
        for kid, vb in field_ids[i]:
            out += struct.pack("<II", kid, len(vb))
            out += vb
    return bytes(out)


def unpack_events(data):
    """Unpack TIR1 bytes back to event dicts. Raises ValueError on corruption."""
    if len(data) < 10:
        raise ValueError("truncated container: %d bytes < 10" % len(data))
    if data[:4] != MAGIC:
        raise ValueError("bad magic: not a TIR1 container")
    count, tabn = struct.unpack_from("<IH", data, 4)
    pos = 10
    strtab = []
    for _ in range(tabn):
        if pos + 2 > len(data):
            raise ValueError("truncated string table")
        (slen,) = struct.unpack_from("<H", data, pos)
        pos += 2
        if pos + slen > len(data):
            raise ValueError("truncated string entry")
        strtab.append(data[pos:pos + slen].decode("utf-8"))
        pos += slen
    events, prev_ms = [], 0
    for _ in range(count):
        if pos + 1 > len(data):
            raise ValueError("truncated record header")
        (level_id,) = struct.unpack_from("<B", data, pos)
        pos += 1
        zu, pos = _get_varint(data, pos)
        prev_ms += _unzigzag(zu)
        if pos + 2 > len(data):
            raise ValueError("truncated name index")
        (nid,) = struct.unpack_from("<H", data, pos)
        pos += 2
        if nid >= tabn:
            raise ValueError("name index %d out of range" % nid)
        (fcount,) = struct.unpack_from("<H", data, pos)
        pos += 2
        fields = {}
        for _ in range(fcount):
            if pos + 8 > len(data):
                raise ValueError("truncated field header")
            kid, vlen = struct.unpack_from("<II", data, pos)
            pos += 8
            if kid >= tabn:
                raise ValueError("key index %d out of range" % kid)
            if pos + vlen > len(data):
                raise ValueError("truncated field body")
            vb = data[pos:pos + vlen]
            pos += vlen
            try:
                fields[strtab[kid]] = vb.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("corrupt utf-8 field bytes: %s" % exc)
        events.append({"ts": prev_ms / 1000.0, "level": LEVEL_NAMES.get(level_id, "INFO"),
                       "event": strtab[nid], "fields": fields})
    return events


def analyzer_view(events, min_level="DEBUG"):
    """Compact, deduplicated text view sized for an LLM context window.
    Numeric-tail collapsing merges high-cardinality instances of one template."""
    min_id = LEVELS.get(min_level.upper(), 0)
    lines, seen, order = [], {}, []
    for e in events:
        if LEVELS.get(e["level"], 1) < min_id:
            continue
        extra = " ".join("%s=%s" % kv for kv in sorted(e["fields"].items()))
        raw = ("%s %s %s" % (e["level"][0], e["event"], extra)).rstrip()
        import re
        tpl = re.sub(r"\d+", "N", raw)
        if tpl in seen:
            seen[tpl] += 1
        else:
            seen[tpl] = 1
            order.append(raw)
    out = list(order)
    if order:
        out.append("# templates: %d, repeat_counts: %s"
                   % (len(order), json.dumps(seen, separators=(",", ":"))))
    return "\n".join(out)


def bench(text, min_level="DEBUG"):
    """Measure raw vs IR bytes, view chars, and wall time of each stage."""
    events = parse_log_lines(text)
    raw_bytes = len(text.encode("utf-8", "replace"))
    t0 = time.perf_counter()
    blob = pack_events(events)
    t1 = time.perf_counter()
    back = unpack_events(blob)
    t2 = time.perf_counter()
    view = analyzer_view(back, min_level)
    t3 = time.perf_counter()
    assert back == events
    return {
        "events": len(events),
        "raw_bytes": raw_bytes,
        "ir_bytes": len(blob),
        "compression_ratio": round(raw_bytes / len(blob), 3) if blob else 0.0,
        "view_chars": len(view),
        "view_vs_raw_pct": round(100.0 * len(view) / raw_bytes, 1) if raw_bytes else 0.0,
        "pack_ms": round((t1 - t0) * 1000.0, 3),
        "unpack_ms": round((t2 - t1) * 1000.0, 3),
        "view_ms": round((t3 - t2) * 1000.0, 3),
    }


def _demo_text(n=2000):
    """Synthetic but realistic: few templates, bounded field cardinality."""
    lines = []
    levels = ["INFO", "INFO", "INFO", "WARN", "ERROR"]
    names = ["auth.login", "db.query", "cache.hit", "http.request", "job.tick"]
    mss = [3, 7, 12, 45, 120]
    for i in range(n):
        lines.append("2026-01-02T03:04:%02dZ %s %s user=u%d ms=%d ok=%s"
                     % (i % 60, levels[i % 5], names[i % 5], i % 10,
                        mss[i % 5], "true" if i % 3 else "false"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="trace-format-bench",
                                 description="Logs -> compact binary IR -> AI-ready view, with benchmarks.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_demo = sub.add_parser("demo", help="run a synthetic benchmark (~1s)")
    p_demo.add_argument("--events", type=int, default=2000)

    p_conv = sub.add_parser("convert", help="log file -> .tir binary IR")
    p_conv.add_argument("infile")
    p_conv.add_argument("outfile")

    p_view = sub.add_parser("view", help=".tir binary -> AI-ready text view")
    p_view.add_argument("infile")
    p_view.add_argument("--min-level", default="DEBUG")

    p_bench = sub.add_parser("bench", help="benchmark a log file")
    p_bench.add_argument("infile")
    p_bench.add_argument("--min-level", default="DEBUG")

    args = ap.parse_args(argv)
    if args.cmd == "demo":
        print(json.dumps(bench(_demo_text(args.events)), indent=2))
        return 0
    if args.cmd == "convert":
        with open(args.infile, "r", encoding="utf-8", errors="replace") as f:
            blob = pack_events(parse_log_lines(f.read()))
        with open(args.outfile, "wb") as f:
            f.write(blob)
        print("wrote %s (%d bytes)" % (args.outfile, len(blob)))
        return 0
    if args.cmd == "view":
        with open(args.infile, "rb") as f:
            try:
                events = unpack_events(f.read())
            except ValueError as exc:
                print("error: %s" % exc, file=sys.stderr)
                return 2
        print(analyzer_view(events, args.min_level))
        return 0
    if args.cmd == "bench":
        with open(args.infile, "r", encoding="utf-8", errors="replace") as f:
            print(json.dumps(bench(f.read(), args.min_level), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
