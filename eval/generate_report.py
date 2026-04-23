#!/usr/bin/env python3
"""Generate evaluation report from eval_results.json."""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import defaultdict

RESULTS_DIR = Path(__file__).resolve().parent / "results"
REPORT_PATH = RESULTS_DIR / "evaluation_report.md"

SCORE_DIMS = ["accuracy", "completeness", "specificity", "hallucination_freedom", "usefulness"]
EFFICIENCY_DIMS = ["input_tokens", "output_tokens", "total_tokens", "latency_s", "search_calls"]
CONDITIONS = ["baseline", "wiki", "agentic", "agentic_wiki"]
CATEGORIES = ["domain_qa", "hypothesis_generation", "experimental_planning",
              "result_interpretation", "academic_writing"]

COND_LABELS = {
    "baseline": "Baseline (Model Only)",
    "wiki": "Wiki-Augmented",
    "agentic": "Agentic (Web Search)",
    "agentic_wiki": "Agentic + Wiki",
}


def load_results() -> list[dict]:
    p = RESULTS_DIR / "eval_results.json"
    with open(p) as f:
        return json.load(f)


def avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def generate_report():
    data = load_results()

    # Group by condition
    by_cond: dict[str, list[dict]] = defaultdict(list)
    by_cond_cat: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in data:
        by_cond[r["condition"]].append(r)
        by_cond_cat[r["condition"]][r["category"]].append(r)

    lines: list[str] = []
    L = lines.append

    L("# ScholarWiki Performance Evaluation Report")
    L("")
    L("## Overview")
    L("")
    L("This report evaluates whether access to a maintained research wiki improves")
    L("LLM performance across five academic research tasks. We compare four conditions:")
    L("")
    L("| Condition | Description |")
    L("|-----------|-------------|")
    L("| **Baseline** | GPT-4.1 with no tools or external context |")
    L("| **Wiki** | GPT-4.1 + relevant ScholarWiki pages as context |")
    L("| **Agentic** | GPT-4.1 + web search tool (OpenAI web_search_preview) |")
    L("| **Agentic + Wiki** | GPT-4.1 + web search + wiki context |")
    L("")
    L("**Judge model:** GPT-5 (scoring each response on 5 dimensions, 1-10 scale)")
    L("")
    L(f"**Tasks evaluated:** {len(set(r['task_id'] for r in data))} tasks across 5 categories")
    L("")

    # ── Overall summary table ──────────────────────────────────────────
    L("## Overall Results")
    L("")
    L("### Quality Scores (1-10, higher is better)")
    L("")
    header = "| Condition | " + " | ".join(d.replace("_", " ").title() for d in SCORE_DIMS) + " | **Avg** |"
    sep = "|" + "|".join(["---"] * (len(SCORE_DIMS) + 2)) + "|"
    L(header)
    L(sep)

    cond_avgs: dict[str, float] = {}
    for cond in CONDITIONS:
        vals = []
        row = f"| **{COND_LABELS[cond]}** |"
        for dim in SCORE_DIMS:
            v = avg([r[dim] for r in by_cond[cond] if isinstance(r.get(dim), (int, float))])
            vals.append(v)
            row += f" {v:.1f} |"
        overall = avg(vals)
        cond_avgs[cond] = overall
        row += f" **{overall:.1f}** |"
        L(row)
    L("")

    # ── Efficiency table ───────────────────────────────────────────────
    L("### Efficiency Metrics")
    L("")
    L("| Condition | Avg Input Tokens | Avg Output Tokens | Avg Total Tokens | Avg Latency (s) | Avg Search Calls |")
    L("|---|---|---|---|---|---|")
    for cond in CONDITIONS:
        items = by_cond[cond]
        L(f"| **{COND_LABELS[cond]}** "
          f"| {avg([r['input_tokens'] for r in items]):.0f} "
          f"| {avg([r['output_tokens'] for r in items]):.0f} "
          f"| {avg([r['total_tokens'] for r in items]):.0f} "
          f"| {avg([r['latency_s'] for r in items]):.1f} "
          f"| {avg([r['search_calls'] for r in items]):.1f} |")
    L("")

    # ── Per-category breakdown ─────────────────────────────────────────
    L("## Per-Category Breakdown")
    L("")

    cat_labels = {
        "domain_qa": "Domain Question Answering",
        "hypothesis_generation": "Hypothesis / Idea Generation",
        "experimental_planning": "Experimental Planning",
        "result_interpretation": "Result Interpretation",
        "academic_writing": "Academic Writing",
    }

    for cat in CATEGORIES:
        L(f"### {cat_labels[cat]}")
        L("")
        L("| Condition | Accuracy | Completeness | Specificity | Halluc. Freedom | Usefulness | Avg | Tokens | Latency |")
        L("|---|---|---|---|---|---|---|---|---|")
        for cond in CONDITIONS:
            items = by_cond_cat[cond][cat]
            if not items:
                continue
            scores = [avg([r[d] for r in items if isinstance(r.get(d), (int, float))]) for d in SCORE_DIMS]
            overall = avg(scores)
            tokens = avg([r["total_tokens"] for r in items])
            latency = avg([r["latency_s"] for r in items])
            L(f"| {COND_LABELS[cond]} "
              + "".join(f"| {s:.1f} " for s in scores)
              + f"| **{overall:.1f}** | {tokens:.0f} | {latency:.1f}s |")
        L("")

    # ── Hallucination analysis ─────────────────────────────────────────
    L("## Hallucination Analysis")
    L("")
    L("| Condition | Tasks with Hallucinations | Total Hallucinated Claims | Avg Halluc. Freedom Score |")
    L("|---|---|---|---|")
    for cond in CONDITIONS:
        items = by_cond[cond]
        tasks_with_halluc = sum(
            1 for r in items
            if r.get("hallucination_details") and len(r["hallucination_details"]) > 0
        )
        total_claims = sum(
            len(r.get("hallucination_details", []))
            for r in items
        )
        avg_score = avg([r["hallucination_freedom"] for r in items if isinstance(r.get("hallucination_freedom"), (int, float))])
        L(f"| **{COND_LABELS[cond]}** | {tasks_with_halluc}/{len(items)} | {total_claims} | {avg_score:.1f}/10 |")
    L("")

    # Specific hallucination examples
    L("### Notable Hallucination Examples")
    L("")
    for r in data:
        details = r.get("hallucination_details", [])
        if details and len(details) > 0:
            L(f"- **{r['task_id']}** ({COND_LABELS[r['condition']]}): {'; '.join(str(d) for d in details[:3])}")
    L("")

    # ── Gold concept coverage ──────────────────────────────────────────
    L("## Gold Concept Coverage")
    L("")
    L("Percentage of expected key concepts covered in each response.")
    L("")
    L("| Condition | Avg Coverage (%) |")
    L("|---|---|")

    # We need the task gold concepts count
    task_gold = {t["id"]: len(t["gold_concepts"]) for t in _get_tasks()}
    for cond in CONDITIONS:
        items = by_cond[cond]
        coverages = []
        for r in items:
            gc = r.get("gold_coverage", [])
            total_gold = task_gold.get(r["task_id"], 5)
            coverages.append(len(gc) / total_gold * 100 if total_gold > 0 else 0)
        L(f"| **{COND_LABELS[cond]}** | {avg(coverages):.1f}% |")
    L("")

    # ── Key findings ───────────────────────────────────────────────────
    L("## Key Findings")
    L("")

    # Determine winners
    best_quality = max(CONDITIONS, key=lambda c: cond_avgs[c])
    best_halluc = max(CONDITIONS, key=lambda c: avg([
        r["hallucination_freedom"] for r in by_cond[c]
        if isinstance(r.get("hallucination_freedom"), (int, float))
    ]))
    most_efficient = min(CONDITIONS, key=lambda c: avg([r["total_tokens"] for r in by_cond[c]]))
    fastest = min(CONDITIONS, key=lambda c: avg([r["latency_s"] for r in by_cond[c]]))

    L(f"1. **Best overall quality:** {COND_LABELS[best_quality]} (avg {cond_avgs[best_quality]:.1f}/10)")
    L(f"2. **Fewest hallucinations:** {COND_LABELS[best_halluc]}")
    L(f"3. **Most token-efficient:** {COND_LABELS[most_efficient]}")
    L(f"4. **Fastest:** {COND_LABELS[fastest]}")
    L("")

    # Wiki improvement over baseline
    if "baseline" in cond_avgs and "wiki" in cond_avgs:
        delta = cond_avgs["wiki"] - cond_avgs["baseline"]
        L(f"- **Wiki vs Baseline:** {'+' if delta > 0 else ''}{delta:.1f} quality improvement")
    if "agentic" in cond_avgs and "agentic_wiki" in cond_avgs:
        delta = cond_avgs["agentic_wiki"] - cond_avgs["agentic"]
        L(f"- **Agentic+Wiki vs Agentic:** {'+' if delta > 0 else ''}{delta:.1f} quality improvement")
    if "baseline" in cond_avgs and "agentic" in cond_avgs:
        delta = cond_avgs["agentic"] - cond_avgs["baseline"]
        L(f"- **Agentic vs Baseline:** {'+' if delta > 0 else ''}{delta:.1f} quality improvement")
    L("")

    # Token efficiency comparison
    baseline_tokens = avg([r["total_tokens"] for r in by_cond["baseline"]])
    wiki_tokens = avg([r["total_tokens"] for r in by_cond["wiki"]])
    agentic_tokens = avg([r["total_tokens"] for r in by_cond["agentic"]])
    agentic_wiki_tokens = avg([r["total_tokens"] for r in by_cond["agentic_wiki"]])

    L("### Token Efficiency Summary")
    L("")
    if agentic_tokens > 0:
        L(f"- Wiki uses **{wiki_tokens/baseline_tokens:.1f}x** the tokens of baseline")
        L(f"- Agentic uses **{agentic_tokens/baseline_tokens:.1f}x** the tokens of baseline")
        L(f"- Agentic+Wiki uses **{agentic_wiki_tokens/baseline_tokens:.1f}x** the tokens of baseline")
        if wiki_tokens > 0 and agentic_tokens > 0:
            L(f"- Wiki achieves its quality at **{wiki_tokens/agentic_tokens:.1f}x** the token cost of agentic")
    L("")

    # ── Per-task details ───────────────────────────────────────────────
    L("## Per-Task Detail")
    L("")
    for task_id in sorted(set(r["task_id"] for r in data)):
        task_results = [r for r in data if r["task_id"] == task_id]
        L(f"### {task_id}")
        L("")
        L("| Condition | Acc | Comp | Spec | Halluc | Use | Tokens | Lat |")
        L("|---|---|---|---|---|---|---|---|")
        for r in sorted(task_results, key=lambda x: CONDITIONS.index(x["condition"])):
            L(f"| {COND_LABELS[r['condition']]} "
              f"| {r.get('accuracy', '?')} | {r.get('completeness', '?')} "
              f"| {r.get('specificity', '?')} | {r.get('hallucination_freedom', '?')} "
              f"| {r.get('usefulness', '?')} | {r['total_tokens']} | {r['latency_s']}s |")
        L("")

    # ── Conclusions ────────────────────────────────────────────────────
    L("## Conclusions")
    L("")
    L("### Does Wiki Access Improve Performance?")
    L("")

    wiki_vs_base = cond_avgs.get("wiki", 0) - cond_avgs.get("baseline", 0)
    wikia_vs_agent = cond_avgs.get("agentic_wiki", 0) - cond_avgs.get("agentic", 0)

    if wiki_vs_base > 0.5:
        L(f"**Yes.** Wiki-augmented responses scored {wiki_vs_base:.1f} points higher than baseline on average.")
    elif wiki_vs_base > 0:
        L(f"**Marginal.** Wiki-augmented responses scored {wiki_vs_base:.1f} points higher than baseline.")
    else:
        L(f"**No clear benefit.** Wiki-augmented responses scored {wiki_vs_base:.1f} vs baseline.")

    L("")
    L("### Does Wiki Add Value on Top of Full Agentic Search?")
    L("")
    if wikia_vs_agent > 0.3:
        L(f"**Yes.** Adding wiki context to agentic search improved scores by {wikia_vs_agent:.1f} points.")
    elif wikia_vs_agent > 0:
        L(f"**Slight benefit.** Adding wiki to agentic search added {wikia_vs_agent:.1f} points.")
    else:
        L(f"**No clear benefit.** Delta was {wikia_vs_agent:.1f} points.")

    L("")
    L("---")
    L("*Generated by ScholarWiki evaluation framework. "
      f"Model under test: GPT-4.1. Judge: GPT-5. "
      f"Tasks: {len(set(r['task_id'] for r in data))}. "
      f"Total API calls: {len(data) * 2} (generation + judging).*")

    report = "\n".join(lines)
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(f"Report written to {REPORT_PATH}")
    return report


def _get_tasks():
    """Import tasks from eval module."""
    from wiki_eval import TASKS
    return TASKS


if __name__ == "__main__":
    generate_report()
