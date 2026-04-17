"""
Apple Silicon LLM benchmark table — Qwen 3 two-tier.

Runtime: GGUF via llama.cpp `llama-bench` (not MLX) so every chip compares
apples-to-apples. MLX would add 30–50% on top for most chips but only
covers a subset of chips with real measurements today.

Source hierarchy:
  1. MEASURED — pulled from `benchmarks/qwen3_measured.csv`. Ground truth.
  2. EXTRAPOLATED_LLAMA2 — for M1–M4 chips we don't have direct Qwen3 data
     for, scale from llama.cpp Discussion #4167 (the canonical Llama-2-7B
     table) via calibrated ratios:
         qwen3_8b_tg = llama2_q4_0_tg × 0.69
         qwen3_8b_pp = llama2_q4_0_pp × 0.81
     Ratios come from averaging the two overlap points: M1 8c (0.78 tg, 0.80 pp)
     and M2 Max 30c (0.61 tg, 0.81 pp).
  3. EXTRAPOLATED_M5 — M5 family has no Llama-2-7B reference in #4167, so we
     anchor to the measured M5 base entry and scale linearly by memory bandwidth.
  4. EXTRAPOLATED_M2MAX — Qwen 3.5 27B has only two measured chips (M2 Max,
     M5 base), so most 27B values are bandwidth-scaled from the M2 Max anchor.

See `thoughts/shared/benchmark_sources.md` for full provenance.
"""

MEASURED = "measured"
EXTRAP_LLAMA2 = "extrapolated_from_llama2_7b_discussion_4167"
EXTRAP_M5 = "extrapolated_from_m5_base_measurement"
EXTRAP_M2MAX = "extrapolated_from_m2_max_measurement"

LLM = {
    "M1":       {"mem_bw_gbs": 68,  "llm_gpu_cores": 8,
                 "qwen3_8b_q4_tg": 11.0, "qwen3_8b_q4_pp": 94.1,
                 "qwen3_27b_q4_tg": 1.6,  "qwen3_27b_q4_pp": 19.6},
    "M1 PRO":   {"mem_bw_gbs": 200, "llm_gpu_cores": 16,
                 "qwen3_8b_q4_tg": 25.1, "qwen3_8b_q4_pp": 215.7,
                 "qwen3_27b_q4_tg": 4.7,  "qwen3_27b_q4_pp": 57.5},
    "M1 MAX":   {"mem_bw_gbs": 400, "llm_gpu_cores": 32,
                 "qwen3_8b_q4_tg": 42.2, "qwen3_8b_q4_pp": 429.3,
                 "qwen3_27b_q4_tg": 9.4,  "qwen3_27b_q4_pp": 115.0},
    "M1 ULTRA": {"mem_bw_gbs": 800, "llm_gpu_cores": 64,
                 "qwen3_8b_q4_tg": 57.8, "qwen3_8b_q4_pp": 834.3,
                 "qwen3_27b_q4_tg": 18.8, "qwen3_27b_q4_pp": 230.0},
    "M2":       {"mem_bw_gbs": 100, "llm_gpu_cores": 10,
                 "qwen3_8b_q4_tg": 15.1, "qwen3_8b_q4_pp": 145.5,
                 "qwen3_27b_q4_tg": 2.4,  "qwen3_27b_q4_pp": 28.8},
    "M2 PRO":   {"mem_bw_gbs": 200, "llm_gpu_cores": 19,
                 "qwen3_8b_q4_tg": 26.8, "qwen3_8b_q4_pp": 276.4,
                 "qwen3_27b_q4_tg": 4.7,  "qwen3_27b_q4_pp": 57.5},
    "M2 MAX":   {"mem_bw_gbs": 400, "llm_gpu_cores": 38,
                 "qwen3_8b_q4_tg": 37.2, "qwen3_8b_q4_pp": 437.5,
                 "qwen3_27b_q4_tg": 9.4,  "qwen3_27b_q4_pp": 115.0},
    "M2 ULTRA": {"mem_bw_gbs": 800, "llm_gpu_cores": 76,
                 "qwen3_8b_q4_tg": 65.0, "qwen3_8b_q4_pp": 1003.2,
                 "qwen3_27b_q4_tg": 18.8, "qwen3_27b_q4_pp": 230.0},
    "M3":       {"mem_bw_gbs": 100, "llm_gpu_cores": 10,
                 "qwen3_8b_q4_tg": 14.7, "qwen3_8b_q4_pp": 151.3,
                 "qwen3_27b_q4_tg": 2.4,  "qwen3_27b_q4_pp": 28.8},
    "M3 PRO":   {"mem_bw_gbs": 150, "llm_gpu_cores": 18,
                 "qwen3_8b_q4_tg": 21.2, "qwen3_8b_q4_pp": 276.8,
                 "qwen3_27b_q4_tg": 3.5,  "qwen3_27b_q4_pp": 43.1},
    "M3 MAX":   {"mem_bw_gbs": 400, "llm_gpu_cores": 40,
                 "qwen3_8b_q4_tg": 45.8, "qwen3_8b_q4_pp": 615.4,
                 "qwen3_27b_q4_tg": 9.4,  "qwen3_27b_q4_pp": 115.0},
    "M3 ULTRA": {"mem_bw_gbs": 800, "llm_gpu_cores": 80,
                 "qwen3_8b_q4_tg": 63.6, "qwen3_8b_q4_pp": 1191.7,
                 "qwen3_27b_q4_tg": 18.8, "qwen3_27b_q4_pp": 230.0},
    "M4":       {"mem_bw_gbs": 120, "llm_gpu_cores": 10,
                 "qwen3_8b_q4_tg": 16.6, "qwen3_8b_q4_pp": 179.2,
                 "qwen3_27b_q4_tg": 2.8,  "qwen3_27b_q4_pp": 34.5},
    "M4 PRO":   {"mem_bw_gbs": 273, "llm_gpu_cores": 20,
                 "qwen3_8b_q4_tg": 35.0, "qwen3_8b_q4_pp": 356.2,
                 "qwen3_27b_q4_tg": 6.4,  "qwen3_27b_q4_pp": 78.5},
    "M4 MAX":   {"mem_bw_gbs": 546, "llm_gpu_cores": 40,
                 "qwen3_8b_q4_tg": 57.3, "qwen3_8b_q4_pp": 717.4,
                 "qwen3_27b_q4_tg": 12.8, "qwen3_27b_q4_pp": 157.0},
    "M5":       {"mem_bw_gbs": 154, "llm_gpu_cores": 10,
                 "qwen3_8b_q4_tg": 9.1,  "qwen3_8b_q4_pp": 153.8,
                 "qwen3_27b_q4_tg": 4.4,  "qwen3_27b_q4_pp": 70.8},
    "M5 PRO":   {"mem_bw_gbs": 307, "llm_gpu_cores": 20,
                 "qwen3_8b_q4_tg": 18.1, "qwen3_8b_q4_pp": 306.6,
                 "qwen3_27b_q4_tg": 8.8,  "qwen3_27b_q4_pp": 141.2},
    "M5 MAX":   {"mem_bw_gbs": 614, "llm_gpu_cores": 40,
                 "qwen3_8b_q4_tg": 36.3, "qwen3_8b_q4_pp": 613.2,
                 "qwen3_27b_q4_tg": 17.5, "qwen3_27b_q4_pp": 282.3},
}

# Per-field provenance. Values: "measured" | "extrapolated_from_<anchor>"
SOURCES = {
    "M1":       {"qwen3_8b_q4_tg": MEASURED,      "qwen3_8b_q4_pp": MEASURED,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M1 PRO":   {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M1 MAX":   {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M1 ULTRA": {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M2":       {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M2 PRO":   {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M2 MAX":   {"qwen3_8b_q4_tg": MEASURED,      "qwen3_8b_q4_pp": MEASURED,
                 "qwen3_27b_q4_tg": MEASURED,     "qwen3_27b_q4_pp": MEASURED},
    "M2 ULTRA": {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M3":       {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M3 PRO":   {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M3 MAX":   {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M3 ULTRA": {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M4":       {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M4 PRO":   {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M4 MAX":   {"qwen3_8b_q4_tg": EXTRAP_LLAMA2, "qwen3_8b_q4_pp": EXTRAP_LLAMA2,
                 "qwen3_27b_q4_tg": EXTRAP_M2MAX, "qwen3_27b_q4_pp": EXTRAP_M2MAX},
    "M5":       {"qwen3_8b_q4_tg": MEASURED,      "qwen3_8b_q4_pp": MEASURED,
                 "qwen3_27b_q4_tg": MEASURED,     "qwen3_27b_q4_pp": MEASURED},
    "M5 PRO":   {"qwen3_8b_q4_tg": EXTRAP_M5,     "qwen3_8b_q4_pp": EXTRAP_M5,
                 "qwen3_27b_q4_tg": EXTRAP_M5,    "qwen3_27b_q4_pp": EXTRAP_M5},
    "M5 MAX":   {"qwen3_8b_q4_tg": EXTRAP_M5,     "qwen3_8b_q4_pp": EXTRAP_M5,
                 "qwen3_27b_q4_tg": EXTRAP_M5,    "qwen3_27b_q4_pp": EXTRAP_M5},
}


def is_measured(chip: str, field: str) -> bool:
    return SOURCES.get(chip, {}).get(field) == MEASURED
