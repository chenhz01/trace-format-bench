# trace-format-bench

**Stop feeding raw log files to your LLM.** Convert once to a compact binary IR, then derive tiny analyzer views. You need this if AI agents regularly re-read multi-MB structured logs.

## Problem

Agents that debug or audit systems burn tokens re-reading the same raw logs on every step, and the raw text is mostly redundancy: repeated field names, repeated templates, wall-clock strings. The insight this repo borrows comes from debugger architecture — RAD Debugger ([EpicGames/raddebugger](https://github.com/EpicGames/raddebugger)) stopped parsing PDB/DWARF every run and instead converts debug info **once** into its own compact RDI intermediate representation, trading a one-time conversion for repeated fast access.

The overlooked angle: nobody treats the *intermediate representation itself* as a standalone, reusable artifact. It is usually locked inside one tool's ecosystem. Here the IR is a plain file format (TIR1) that any analyzer — human script or LLM agent — can consume without re-ingesting raw text.

## How it works

1. `parse_log_lines` — tolerant parse of `TIMESTAMP LEVEL event key=value ...` lines.
2. `pack_events` — encodes into **TIR1**: a string table (event names + field keys stored once), zigzag-varint *delta* timestamps, level bytes, length-prefixed values. Lossless round-trip guaranteed.
3. `analyzer_view` — derives a template-collapsed, deduplicated text view with repeat counts, sized for an LLM context window.
4. `bench` — measures raw vs IR bytes, view size, and per-stage wall time in one run.

## Quickstart (~5 s, pure stdlib, Python 3.8+)

```bash
python self_test.py                    # 22 checks, ~8 s on a laptop (as of 2026-10-11)
python trace_format_bench.py demo      # synthetic 2000-event benchmark, ~1 s
python trace_format_bench.py convert app.log app.tir
python trace_format_bench.py view app.tir --min-level WARN
```

Measured results (repro: `python trace_format_bench.py demo`, Python 3.12, Windows, as of 2026-10-11):

| Input | Raw bytes | TIR1 bytes | Ratio | View vs raw | Pack time |
|---|---|---|---|---|---|
| 2,000 events | 117,466 | 78,385 | **1.50x** | **0.7%** | ~14 ms |
| 100,000 events | 5,873,333 | 3,915,085 | **1.50x** | <0.1% | ~740 ms |

The headline for agents is the *view*: the analyzer view collapses to under 1% of raw bytes, so an LLM reads ~800 chars instead of ~117 KB. Confidence: **High (≥80%)** for the byte-count claims — they are deterministic and reproduced by `self_test.py`. The IR is **not** a general-purpose compressor (see Limits); confidence **Medium (60–79%)** that real-world production logs with bounded template cardinality see ≥1.3x IR compression [estimated — depends entirely on your log shapes].

## Why not X?

| Alternative | Why this still wins |
|---|---|
| Re-send raw logs to the LLM every step | Pays full tokens every time; the view is ~0.7% of raw size on repetitive logs |
| gzip / zstd the logs | Great storage compression, but opaque bytes: an agent must decompress the *whole* file and re-read raw text anyway. TIR1's view is directly LLM-readable and filterable by level without decoding everything |
| SQLite / DuckDB log store | Better for real querying, but schema setup + SQL round-trips per step; this is a zero-dependency single file you can hand to any agent, and the bench quantifies exactly what you save |
| Parquet + Arrow | Columnar analytics at scale; heavy dependency footprint, overkill for agent context prep where the unit of work is "one trace file" |
| Generic log parsers (logparser, drain3) | Template-mining focus, no binary IR, no conversion-cost bench, no lossless round-trip guarantee |

## Minimal Fallback (PLAN B)

No Python? No problem — the format is documented in `trace_format_bench.py` (module docstring + `pack_events`). Any tool that can read a string table and varints (a 40-line script in any language, or a one-shot LLM prompt over a hexdump) can decode a `.tir` file. And if you never convert at all: `analyzer_view`'s trick — template-collapse with digit runs replaced by `N` plus repeat counts — works on raw text with plain `sed`/`awk` and already cuts agent input ~10x on repetitive logs [estimated].

## Design Trade-offs

Priority order when things conflict: **correctness (lossless round-trip) > measurability (bench always reported) > speed > compression ratio > format elegance.** Consequences: the IR carries an assertion-checked round-trip in every bench run (correctness gate), and we do *not* chase gzip-level ratios with entropy coding — that would trade simplicity and streaming decode for bytes, which this tool explicitly does not optimize for.

## Limits & Second-order Effects

- **High-cardinality logs compress poorly.** If every line is unique, TIR1 can be *larger* than raw text (length prefixes + string-table overhead). The bench tells you before you commit.
- **The view hides detail on purpose.** Template collapsing merges instances; an agent that needs the exact 3rd occurrence's timestamp must unpack the IR, not the view. Second-order effect: teams may start trusting collapsed views in postmortems and mis-attribute rare one-off anomalies that were folded into a template count.
- **Lock-in risk of a homegrown format.** TIR1 is deliberately trivial (string table + varints + length prefixes), but it is still v1 and may change; keep your raw logs.
- **Speed claims age.** All timings are from one laptop on one date; your disk/CPU will differ. Re-run `demo` yourself.

## FAQ

**Q: Is this a log compressor?**
A: No. It is a *representation converter with a built-in bench*. Compression is a side effect; the product is "cheap repeated analysis."

**Q: Does the round-trip preserve everything?**
A: `self_test.py` asserts full identity on round-trip for all fixtures, including a 500 KB field value and 100k events. Float timestamps are stored as integer milliseconds — sub-millisecond precision is truncated (documented lossiness).

**Q: When NOT to use this?**
A: (Socratic check.) Do **not** use it when (1) your logs are one-off, high-cardinality, or tiny (<10 KB) — conversion overhead exceeds benefit; (2) you need real queries/aggregations — use SQLite or DuckDB; (3) your consumer is a human tailing a file — `grep` is fine; (4) sub-millisecond timestamp fidelity matters — TIR1 truncates to milliseconds.

**Q: Why invent a format instead of using protobuf/flatbuffers?**
A: Zero-dependency goal. TIR1 is ~80 lines of stdlib struct code, inspectable in one screen. The bench exists partly to verify that this simplicity does not cost much.

## [Core Assumptions]

1. Structured logs in agentic workflows follow repeated templates with bounded field cardinality; if not, the bench will show ratio ≤ 1 and you should not convert.
2. The dominant cost for LLM log analysis is input tokens, not parse CPU time; therefore view size matters more than pack speed.
3. Sub-millisecond timestamp precision is dispensable for agent-level debugging (millisecond granularity retained).
4. Consumers can run Python (or port the ~80-line format); there is no requirement for a shared binary across languages in v1.

---
Topics: `logging` `benchmark` `llm` `ai-agents` `intermediate-representation` `token-optimization` `observability`

Status: v0.1.1 reference implementation. Pure stdlib. MIT. All performance numbers reproducible via `python trace_format_bench.py demo` and `python self_test.py`. Timings as of 2026-10-11.

Inspired by the "convert, don't re-parse" architecture of Epic Games' RAD Debugger (https://github.com/EpicGames/raddebugger); no code or text from that repository is used here.
