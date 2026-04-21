"""
Pre-flight cost estimation and cap enforcement.

Pricing (OpenAI Batch API, 50% off standard):
  GPT-4.1 batch: $1.00/M input,  $4.00/M output
  GPT-5   batch: $2.00/M input,  $8.00/M output
  GPT-4.1 std:   $2.00/M input,  $8.00/M output  (synchronous calls)

Measured averages from production runs (15 papers):
  Extraction input per module request: ~8,000 tokens
  Extraction output per module:
    knowledge: ~2,600 tokens
    roadmap:   ~1,917 tokens
    logic:     ~1,550 tokens
    writing:   ~1,188 tokens
    experiment:~3,103 tokens
  Concept synthesis:  ~4,500 in / ~1,500 out per page  (GPT-5 batch)
  Pattern synthesis:  ~5,000 in / ~2,600 out per page  (GPT-5 batch)
  Style synthesis:    ~3,000 in / ~1,500 out per page  (GPT-4.1 batch)
"""
from __future__ import annotations

from dataclasses import dataclass

# ── Pricing per token ────────────────────────────────────────────────────────
_GPT41_BATCH_IN  = 1.00 / 1_000_000
_GPT41_BATCH_OUT = 4.00 / 1_000_000
_GPT5_BATCH_IN   = 2.00 / 1_000_000
_GPT5_BATCH_OUT  = 8.00 / 1_000_000
_GPT41_STD_IN    = 2.00 / 1_000_000
_GPT41_STD_OUT   = 8.00 / 1_000_000

# ── Per-module output averages (tokens) ─────────────────────────────────────
_EXT_OUTPUT_AVG = {
    "knowledge": 2606,
    "roadmap":   1917,
    "logic":     1550,
    "writing":   1188,
    "experiment": 3103,
}
_EXT_INPUT_AVG = 8000   # tokens per module request
_EXT_MODULES = 5


@dataclass
class CostEstimate:
    phase: str
    input_tokens: int
    output_tokens: int
    cost_usd: float

    def __str__(self) -> str:
        return (
            f"{self.phase}: "
            f"{self.input_tokens:,} in / {self.output_tokens:,} out → "
            f"${self.cost_usd:.3f}"
        )


def estimate_extraction_cost(n_papers: int) -> CostEstimate:
    """Estimate GPT-4.1 batch cost for extracting n papers (5 modules each)."""
    n_requests = n_papers * _EXT_MODULES
    input_tokens  = n_requests * _EXT_INPUT_AVG
    output_tokens = n_requests * sum(_EXT_OUTPUT_AVG.values()) // len(_EXT_OUTPUT_AVG)
    cost = input_tokens * _GPT41_BATCH_IN + output_tokens * _GPT41_BATCH_OUT
    return CostEstimate("extraction", input_tokens, output_tokens, cost)


def estimate_linking_cost(
    n_concepts: int,
    n_patterns: int,
    n_styles: int,
    n_pass2_concepts: int = 10,
) -> CostEstimate:
    """Estimate cost for a full linking run (Pass 1 + Pass 2 + styles).

    Pass 1  — GPT-5 batch: concept + pattern synthesis with connections
    Pass 2  — GPT-5 batch: promoted single-paper concepts (default 10 mid estimate)
    Styles  — GPT-4.1 batch
    Promo   — GPT-4.1 std: single synchronous promotion-check call
    """
    # Pass 1: concepts + patterns (GPT-5 batch)
    # Extra +800 in / +600 out per page for connections frontmatter
    p1_concept_in  = n_concepts  * (4500 + 800)
    p1_concept_out = n_concepts  * (1500 + 600)
    p1_pattern_in  = n_patterns  * (5000 + 800)
    p1_pattern_out = n_patterns  * (2600 + 600)

    p1_in  = p1_concept_in  + p1_pattern_in
    p1_out = p1_concept_out + p1_pattern_out
    p1_cost = p1_in * _GPT5_BATCH_IN + p1_out * _GPT5_BATCH_OUT

    # Styles (GPT-4.1 batch)
    sty_in  = n_styles * (3000 + 800)
    sty_out = n_styles * (1500 + 600)
    sty_cost = sty_in * _GPT41_BATCH_IN + sty_out * _GPT41_BATCH_OUT

    # Pass 2 promotion check (GPT-4.1 synchronous)
    promo_cost = 4500 * _GPT41_STD_IN + 600 * _GPT41_STD_OUT

    # Pass 2 synthesis (GPT-5 batch)
    p2_in  = n_pass2_concepts * 4000
    p2_out = n_pass2_concepts * 2000
    p2_cost = p2_in * _GPT5_BATCH_IN + p2_out * _GPT5_BATCH_OUT

    total_in  = p1_in + sty_in + p2_in
    total_out = p1_out + sty_out + p2_out
    total_cost = p1_cost + sty_cost + promo_cost + p2_cost

    return CostEstimate("linking", total_in, total_out, total_cost)


class CostCapExceeded(RuntimeError):
    """Raised when estimated cost exceeds the configured cap."""
    pass


def check_extraction_cap(n_papers: int, cap_usd: float) -> CostEstimate:
    """Estimate extraction cost and raise CostCapExceeded if over cap.

    Returns the estimate if within cap.
    """
    est = estimate_extraction_cost(n_papers)
    if est.cost_usd > cap_usd:
        raise CostCapExceeded(
            f"Extraction estimate ${est.cost_usd:.2f} exceeds cap ${cap_usd:.2f} "
            f"for {n_papers} papers. Reduce paper count or raise extraction.max_cost_usd."
        )
    return est


def check_linking_cap(
    n_concepts: int,
    n_patterns: int,
    n_styles: int,
    cap_usd: float,
    n_pass2_concepts: int = 10,
) -> CostEstimate:
    """Estimate linking cost and raise CostCapExceeded if over cap.

    Returns the estimate if within cap.
    """
    est = estimate_linking_cost(n_concepts, n_patterns, n_styles, n_pass2_concepts)
    if est.cost_usd > cap_usd:
        raise CostCapExceeded(
            f"Linking estimate ${est.cost_usd:.2f} exceeds cap ${cap_usd:.2f} "
            f"({n_concepts} concepts, {n_patterns} patterns, {n_styles} styles, "
            f"{n_pass2_concepts} pass2 concepts). Raise linking.max_cost_usd to proceed."
        )
    return est
