# Changelog

## v0.1.1 — 2026-10-11 (self-audit revision, round 2)

Iterated against ALIGNMENT-16 (rules 85-100). Changes:

- **Correctness (round-2 fix, caught by edge-case tests):** field value length widened u16 -> u32 after the 500 KB single-field edge test crashed with `struct.error`; container minimum-size guard raised to 10 bytes to match the new header.
- **Format density (~30% smaller IR):** v0.1.0 stored one f64 timestamp and full field-key text per record. v0.1.1 adds a string table (event names + field keys stored once) and zigzag-varint *delta* timestamps; measured compression on the 2,000-event synthetic bench improved from below 1.0x (IR larger than raw) to a stable **1.50x**, and the analyzer view now template-collapses to ~0.7% of raw bytes.
- **Honest numbers:** all README performance figures now come from `self_test.py` / `demo` runs with reproduction commands and an as-of date; unmeasurable claims explicitly tagged `[estimated]`.
- **README completeness:** added Minimal Fallback, Design Trade-offs priority order, Limits & Second-order Effects, FAQ with "When NOT to use", [Core Assumptions] (4 items), and two explicit confidence ratings.
- self_test: 22/22 PASS across functional / error-path / extreme-edge families (empty input, 100k-event superlong input, 500 KB field, corrupted magic/truncation/utf-8).

## v0.1.0 — 2026-10-11 (initial draft)

- TIR1 binary IR: pack/unpack with lossless round-trip assertion.
- Tolerant structured-log parser (`TIMESTAMP LEVEL event key=value`).
- Template-collapsing analyzer view for LLM context windows.
- Bench CLI (`demo`, `convert`, `view`, `bench`) quantifying raw vs IR bytes and per-stage timings.
- self_test with functional, error-path, and extreme-edge families (19 checks at draft time).
