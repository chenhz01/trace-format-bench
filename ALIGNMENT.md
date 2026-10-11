# Alignment Audit (Rules 85-100 / 16 items) — trace-format-bench v0.1.1

Audited: 2026-10-11, against ALIGNMENT-16.md.

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Safety/Ethics section | N/A | Non-security repo (log benchmarking); no reverse-engineering, OSINT, or vuln content |
| 2 | Privacy (no secrets/real names) | PASS | grep for `sk-\|ghp_\|api[_-]?key` = 0 hits; only contact-adjacent string is none; no real names; MIT copyright "zhengming contributors" |
| 3 | Copyright boundary | PASS | No >50-char contiguous text from EpicGames/raddebugger; README links source repo and paraphrases its architecture in 2 sentences; LICENSE (MIT) present |
| 4 | Fact-check annotations | PASS | All numbers from `python trace_format_bench.py demo` / `self_test.py` (1.50x ratio, 0.7% view, ~14 ms pack, 100k in ~740 ms) with repro commands + as-of 2026-10-11; unmeasurable claims tagged [estimated] |
| 5 | Confidence grading | PASS | Two explicit ratings: High (byte counts, deterministic + reproduced) and Medium (real-world ≥1.3x compression, [estimated]) with one-line rationale each |
| 6 | Minimal Fallback (PLAN B) | PASS | "Minimal Fallback (PLAN B)" section: format is 40-line-decodable without Python; sed/awk template-collapse trick on raw text |
| 7 | Quickstart timing | PASS | "~5 s" header + per-command estimates (~8 s self-test, ~1 s demo); staged minimal→full path (self-test → demo → convert → view) |
| 8 | Design trade-offs / priorities | PASS | "Design Trade-offs" declares order: correctness > measurability > speed > compression > elegance, with consequences |
| 9 | CHANGELOG ≥2 entries | PASS | v0.1.0 (draft) + v0.1.1 (self-audit revision) with named improvements incl. u16→u32 fix and ~30% IR density gain |
| 10 | Exemption (session rule 94) | N/A | Session-level rule; not applicable to static repo content |
| 11 | Time-sensitive data dated | PASS | Timings marked "as of 2026-10-11" in Quickstart, tables, and Status footer |
| 12 | Core Assumptions ≥3 | PASS | 4 assumptions listed under [Core Assumptions] (template regularity, token-cost dominance, ms precision OK, single-language v1) |
| 13 | Logic triple (functional/error/edge) | PASS | self_test.py: A functional (round-trip, CLI, bench), B error paths (bad magic, truncation, corrupt utf-8, missing file), C extreme (empty, 100k events, 500 KB field, garbage lines) — 22/22 PASS |
| 14 | FAQ "When NOT to use" | PASS | FAQ contains Socratic "When NOT to use?" with 4 concrete anti-use cases |
| 15 | ≥2 content iterations | PASS | v0.1.0 → v0.1.1 recorded in CHANGELOG; round-2 dimension "correctness + completeness": IR format rewritten (string table + varint deltas, sub-1.0x → 1.50x ratio, >30% density gain) and 5 README sections added |
| 16 | ≤60-word first screen | PASS | Opening paragraph is 33 words incl. one-line-what + need-judgment sentence |

Additional: **Limits & Second-order Effects** present (rule 16 second-order thinking): template collapsing may hide one-off anomalies in postmortems; homegrown-format lock-in; bench-before-commit guidance.
