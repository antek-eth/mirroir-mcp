# Apple Silicon LLM benchmark sources

Provenance log for the Qwen3 two-tier benchmark table in `benchmarks/llm_table.py`.
Replaces the stale Llama-2-7B numbers from llama.cpp Discussion #4167 that lived in
`pipeline.py` before 2026-04-17.

## Runtime + model choices

- **Runtime**: GGUF via `llama-bench` (llama.cpp). MLX would be 30–50 % faster on
  Apple Silicon but only a fraction of the 18 chip variants has published MLX
  numbers. Keeping one runtime makes the whole table comparable.
- **Floor model**: Qwen 3 8B @ Q4_K_M. Fits in 8 GB+ unified memory. Current
  community-consensus workhorse as of 2026-04 (replaced Llama 3 8B over winter).
- **Pro-tier model**: Qwen 3.5 27B @ Q4_K_M. Requires ≥ 32 GB RAM with headroom
  for KV cache (the pipeline gates this at `ram_gb >= 32`).
- **Metrics**: `tg128` (decode tok/s, memory-bandwidth-bound) and `pp512`
  (prefill tok/s, compute-bound). Standard `llama-bench` output.

## Measured anchor points

| Chip          | CPU/GPU/RAM    | Runtime | Quant   | Model         | tg128 | pp512 | Source |
|---------------|----------------|---------|---------|---------------|-------|-------|--------|
| M1            | 8c / 7g / 16GB | GGUF    | Q4_K_M  | Qwen 3 8B     | 11.0  | 94.1  | [mac-llm-bench M1 base](https://github.com/enescingoz/mac-llm-bench/blob/main/results/m1/base/README.md) |
| M2 MAX        | 12c / 30g / 32GB | GGUF  | Q4_K_M  | Qwen 3 8B     | 37.2  | 437.5 | [mac-llm-bench M2 Max](https://github.com/enescingoz/mac-llm-bench/blob/main/results/m2/max/README.md) |
| M5            | 10c / 10g / 32GB | GGUF  | Q4_K_M  | Qwen 3 8B     | 9.1   | 153.8 | [mac-llm-bench M5 base](https://github.com/enescingoz/mac-llm-bench/blob/main/results/m5/base/README.md) |
| M2 MAX        | 12c / 30g / 32GB | GGUF  | Q4_K_M  | Qwen 3.5 27B  | 9.4   | 115.0 | same |
| M5            | 10c / 10g / 32GB | GGUF  | Q4_K_M  | Qwen 3.5 27B  | 4.4   | 70.8  | same |

All pulled 2026-04-17 and logged in `benchmarks/qwen3_measured.csv`.

## Extrapolation rules

When a chip has no direct Qwen3 measurement, the table falls back to one of three
formulas. Every extrapolated field carries a `_source` tag of `extrapolated_from_*`
so the UI can mark it with a `*`.

### EXTRAP_LLAMA2 — for M1/M2/M3/M4 chips without Qwen3 data

Scale from llama.cpp [Discussion #4167](https://github.com/ggml-org/llama.cpp/discussions/4167)
Llama-2-7B Q4_0 numbers via calibrated ratios:

```
qwen3_8b_q4_tg = llama2_7b_q4_0_tg × 0.69
qwen3_8b_q4_pp = llama2_7b_q4_0_pp × 0.81
```

Ratios come from the two overlap points we have measured data for:

| Chip   | Llama2 Q4_0 tg / pp | Qwen3 8B tg / pp | Ratio tg / pp |
|--------|---------------------|------------------|---------------|
| M1 8c  | 14.15 / 117.96      | 11.0 / 94.1      | 0.78 / 0.80   |
| M2 Max 30c | 60.99 / 537.6   | 37.2 / 437.5     | 0.61 / 0.81   |

Average tg ratio ≈ 0.69 (Qwen 3 8B is ~21 % more params than Llama-2-7B and uses
Q4_K_M which is ~12 % larger than Q4_0, so ~35 % more weight bytes to stream per
decode step — ratio of 0.69 lines up with that).

**Known weakness**: ratios diverge by ~14 pp between the two anchors. Per-chip
estimates may be off by ±15 %.

### EXTRAP_M5 — for M5 Pro / M5 Max

Discussion #4167 has no Llama-2-7B numbers for the M5 family (still marked
"awaiting contributions"). Extrapolate from measured M5 base, linear in memory
bandwidth:

```
qwen3_8b_q4_tg  = 9.1  × (bw_target / 154)
qwen3_8b_q4_pp  = 153.8 × (bw_target / 154)
qwen3_27b_q4_tg = 4.4   × (bw_target / 154)
qwen3_27b_q4_pp = 70.8  × (bw_target / 154)
```

**Known weakness**: the M5 base `pp512 = 153.8` anchor is suspiciously low for its
154 GB/s bandwidth (M4 base at 120 GB/s does 221 Llama-2 Q4_0 pp, or ~179 Qwen3
predicted). Early GGUF support on M5 may not yet exploit the Neural Accelerators
that MLX does. Expect real M5 Pro / Max numbers to come in higher when the
community contributes them. See [r/LocalLLaMA "Qwen3-Coder-Next M5 Max"](https://www.reddit.com/r/LocalLLaMA/comments/1s6wsy7/m5max_macbook_pro_128gb_qwen3_coder_next_8bit/)
(2026-03-29, 74 upvotes) which reports ~72 tok/s on the 8-bit variant via MLX.

### EXTRAP_M2MAX — for Qwen 3.5 27B on non-anchor chips

Only two measured 27B points exist (M2 Max, M5 base). Extrapolate linearly from
the M2 Max anchor using bandwidth:

```
qwen3_27b_q4_tg = 9.4 × (bw_target / 400)
qwen3_27b_q4_pp = 115 × (bw_target / 400)
```

**Known weakness**: at very low bandwidth (M1 at 68 GB/s) this predicts ~1.6 tok/s
which is technically accurate but practically unusable. At very high bandwidth
(800 GB/s Ultra chips) it predicts ~18.8 tok/s which doesn't account for
bandwidth-saturation effects seen in the few measured Ultra data points. Both
extremes should be treated as order-of-magnitude only.

## Secondary sources consulted (not yet integrated)

These have partial data that could be folded in as more `measured` anchors later:

- **[Silicon Score bench](https://siliconscore.com/bench/)** — 12 field reports for
  Qwen 3.5 27B, best-in-class 31.6 tok/s tg / 222 tok/s pp on M5 Max 128GB.
  Runtime ambiguous (may be MLX), which is why it's not yet used.
- **[SiliconBench.radicchio.page](https://siliconbench.radicchio.page/)** — claims
  broader Apple Silicon coverage, worth scraping for a future update.
- **[apxml.com / sitepoint 2026 guides](https://apxml.com/posts/best-local-llms-apple-silicon-mac)** —
  point measurements on various M-series chips, mostly Ollama.
- **[willitrunai.com](https://www.willitrunai.com/can-run/qwen-3-8b-on-m3-max-128gb)** —
  Qwen 3 8B on M3 Max 128GB ~53 tok/s. Runtime not disclosed in the summary
  (likely Ollama + MLX) so not used as an anchor.
- **[llama.cpp Discussion #4167](https://github.com/ggml-org/llama.cpp/discussions/4167)** —
  the canonical Llama-2-7B reference used as calibration anchor for
  EXTRAP_LLAMA2. Rigidly Llama-2-only by moderator policy.

## When to refresh

The extrapolated values are estimates bandwidth-anchored to 2 real measurements.
Refresh when any of the following happens:

- mac-llm-bench adds a new chip variant (M1 Pro/Max/Ultra, M3 family, M4 family,
  M5 Pro/Max) — replace the matching extrapolated row with measured values and
  recompute ratios
- A new floor/pro-tier model replaces Qwen 3 / 3.5 in community consensus —
  regenerate the table against the new pair, keeping the same tg128 / pp512
  protocol
- llama.cpp ships a major perf improvement that shifts the ratio (past 18 months
  has seen ~15 % lift per the M2 Ultra time-series in Discussion #4167)
