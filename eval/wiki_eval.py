#!/usr/bin/env python3
"""
ScholarWiki Performance Evaluation
===================================
Compares 4 conditions:
  1. baseline     — model only, no tools or context
  2. wiki         — model + relevant wiki pages as context
  3. agentic      — model + web_search tool (OpenAI responses API)
  4. agentic_wiki — model + web_search + wiki context

Tasks: domain QA, hypothesis generation, experimental planning,
       result interpretation, academic writing

Metrics: quality, hallucination, citation grounding, token usage, latency
Judge: GPT-5
"""

from __future__ import annotations
import json, time, os, sys, hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

from openai import OpenAI

# ── paths ──────────────────────────────────────────────────────────────
WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

client = OpenAI()

MODEL = "gpt-4.1"          # model under test
JUDGE = "gpt-5"            # evaluation judge
SEARCH_CONTEXT_SIZE = "medium"

# ── evaluation tasks ───────────────────────────────────────────────────

TASKS: list[dict[str, Any]] = [
    # ── Domain Question Answering ──────────────────────────────────────
    {
        "id": "qa_1",
        "category": "domain_qa",
        "prompt": (
            "What is the difference between multimodal alignment and multimodal "
            "integration in single-cell foundation models? When does alignment "
            "alone become insufficient?"
        ),
        "wiki_queries": ["multimodal integration", "multimodal modeling", "foundation models"],
        "gold_concepts": [
            "alignment places modalities in shared space",
            "integration exploits complementarities",
            "synergistic integration score scales with spatial range",
            "alignment is necessary but insufficient",
            "two-stage training: alignment then integration",
        ],
    },
    {
        "id": "qa_2",
        "category": "domain_qa",
        "prompt": (
            "How does transfer learning work differently in biological sequence "
            "understanding versus vision-language models? Why does instruction "
            "tuning alone fail for biology?"
        ),
        "wiki_queries": ["transfer learning", "instruction tuning", "pretraining"],
        "gold_concepts": [
            "domain-adaptive pretraining is required for biology",
            "instruction tuning alone performs near chance on multi-omics",
            "staged pipeline: pretrain then instruct then reason",
            "vision-language uses feature alignment then instruction tuning",
            "representation alignment must precede task-format conditioning",
        ],
    },
    {
        "id": "qa_3",
        "category": "domain_qa",
        "prompt": (
            "What is HyenaDNA's approach to genomic sequence modeling, and how "
            "does it compare to transformer-based genomic models in terms of "
            "parameter efficiency and context length?"
        ),
        "wiki_queries": ["foundation models", "in context learning", "transfer learning"],
        "gold_concepts": [
            "long-range operators replace dense attention",
            "million-token context at single-nucleotide resolution",
            "1500x fewer parameters than prior transformers",
            "3200x less pretraining data",
            "in-context learning via soft prompts",
        ],
    },
    # ── Hypothesis Generation ──────────────────────────────────────────
    {
        "id": "hyp_1",
        "category": "hypothesis_generation",
        "prompt": (
            "Based on the current understanding of cross-species transfer learning "
            "in single-cell biology and multimodal integration, propose 3 novel "
            "research hypotheses about building a universal cell foundation model "
            "that works across species, modalities, and tissue types."
        ),
        "wiki_queries": [
            "transfer learning", "cross species analysis", "multimodal integration",
            "foundation models", "zero shot learning",
        ],
        "gold_concepts": [
            "cross-species transfer via conserved biology",
            "multimodal synergy beyond alignment",
            "zero-shot cell type recognition",
            "curriculum learning for integration",
            "inductive bias vs scale tradeoff",
        ],
    },
    {
        "id": "hyp_2",
        "category": "hypothesis_generation",
        "prompt": (
            "Given the known failure modes of visual instruction tuning (hallucination, "
            "format brittleness, forgetting), propose 2 hypotheses for how these "
            "problems might manifest differently when the same paradigm is applied "
            "to single-cell QA instruction tuning."
        ),
        "wiki_queries": [
            "visual instruction tuning", "single cell qa instruction",
            "instruction tuning", "catastrophic forgetting",
        ],
        "gold_concepts": [
            "hallucination in VIT from synthetic data",
            "input format brittleness",
            "gene token vs image token differences",
            "catastrophic forgetting during multimodal tuning",
            "template sensitivity in QA",
        ],
    },
    # ── Experimental Planning ──────────────────────────────────────────
    {
        "id": "exp_1",
        "category": "experimental_planning",
        "prompt": (
            "Design an experiment to test whether adding a self-supervised "
            "masked-gene recovery objective alongside supervised QA training "
            "improves cross-species cell type annotation accuracy. Include "
            "specific baselines, controls, metrics, and dataset requirements."
        ),
        "wiki_queries": [
            "single cell qa instruction", "transfer learning",
            "zero shot learning", "batch effect correction",
        ],
        "gold_concepts": [
            "masked gene recovery as self-supervised objective",
            "FQA construction with multiple templates",
            "cross-species evaluation on held-out species",
            "ablation: with and without mask loss",
            "negative controls with shuffled labels",
        ],
    },
    {
        "id": "exp_2",
        "category": "experimental_planning",
        "prompt": (
            "Design a benchmark study to evaluate whether RL-based preference "
            "alignment (as done in GLM-4.5V) would benefit single-cell foundation "
            "models the way it benefits vision-language models. What would the "
            "reward signal look like for biology?"
        ),
        "wiki_queries": [
            "fine tuning", "foundation models", "transfer learning",
            "model validation", "interpretability",
        ],
        "gold_concepts": [
            "cross-domain RL spillover in VLMs",
            "preference-based alignment doubled motif scaffolding success",
            "staged pipeline: pretrain → instruct → RL",
            "biological reward signals differ from human preference",
            "need ablation of RL vs instruction-only",
        ],
    },
    # ── Result Interpretation ──────────────────────────────────────────
    {
        "id": "interp_1",
        "category": "result_interpretation",
        "prompt": (
            "A researcher reports that their single-cell foundation model achieves "
            "93% accuracy on cell type classification in human brain tissue but "
            "only 61% when tested zero-shot on macaque brain tissue. They used "
            "instruction tuning without domain-adaptive pretraining. "
            "Interpret these results and suggest what might explain the gap."
        ),
        "wiki_queries": [
            "transfer learning", "zero shot learning",
            "cross species analysis", "instruction tuning",
        ],
        "gold_concepts": [
            "instruction tuning alone fails without domain pretraining",
            "cross-species transfer requires conserved biology in representations",
            "scMOBA achieved 93.1% subclass zero-shot with pretraining",
            "domain mismatch between species",
            "need continued pretraining on cross-species data",
        ],
    },
    {
        "id": "interp_2",
        "category": "result_interpretation",
        "prompt": (
            "A team finds that their multimodal cell model performs well on cell "
            "type classification (which is a per-cell task) but poorly on "
            "neighborhood cell type regression at distances >50µm. The model "
            "uses only alignment (shared embedding) without integration layers. "
            "Explain what's happening and suggest a fix."
        ),
        "wiki_queries": [
            "multimodal integration", "spatial transcriptomics",
            "multimodal fusion", "foundation models",
        ],
        "gold_concepts": [
            "synergistic integration score rises with spatial range",
            "alignment is insufficient for distributed context tasks",
            "need integration beyond shared embedding",
            "two-stage training: alignment then LoRA integration",
            "per-cell tasks don't require cross-modal synergy",
        ],
    },
    # ── Academic Writing ───────────────────────────────────────────────
    {
        "id": "write_1",
        "category": "academic_writing",
        "prompt": (
            "Write a Related Work section (2–3 paragraphs) for a paper proposing "
            "a new multi-omics foundation model that combines scRNA-seq and "
            "snATAC-seq for cross-species brain cell type annotation. Cover "
            "existing single-cell foundation models, multimodal integration "
            "approaches, and cross-species transfer learning."
        ),
        "wiki_queries": [
            "foundation models", "transfer learning", "multimodal integration",
            "single cell qa instruction", "cross species analysis",
            "batch effect correction",
        ],
        "gold_concepts": [
            "Geneformer pretrained on 30M transcriptomes",
            "scMOBA cross-species brain agent",
            "alignment vs integration distinction",
            "HyenaDNA long-range genomic modeling",
            "staged transfer: pretrain → instruct → adapt",
            "specific paper citations",
        ],
    },
    {
        "id": "write_2",
        "category": "academic_writing",
        "prompt": (
            "Write an Introduction paragraph (≈200 words) for a paper about "
            "applying visual instruction tuning methodology to biological data. "
            "Motivate why the VIT paradigm is promising for biology, acknowledge "
            "known failure modes, and state the gap your paper addresses."
        ),
        "wiki_queries": [
            "visual instruction tuning", "instruction tuning",
            "single cell qa instruction", "foundation models",
        ],
        "gold_concepts": [
            "two-stage VIT pipeline: alignment then instruction tuning",
            "success in vision-language domain",
            "known failure modes: hallucination, format brittleness",
            "biology requires domain-adaptive pretraining",
            "gap: adapting VIT to biological sequences",
        ],
    },
]


# ── wiki retrieval ─────────────────────────────────────────────────────
# We import the project's own search_wiki and read_page functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from scholarwiki.mcp.tools import search_wiki, read_page, get_bibliography
import re as _re

_WIKILINK_RE = _re.compile(r"\[\[([^\]]+)\]\]")


def _build_citation_map(slugs: list[str]) -> dict[str, str]:
    """Build a mapping from slug → APA citation string using wiki source pages."""
    import yaml
    cmap: dict[str, str] = {}
    for slug in slugs:
        content = read_page(WIKI_DIR, "sources", slug)
        if not content:
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1])
        except Exception:
            continue
        # Build short citation: "Last et al. (Year)"
        authors = fm.get("authors", [])
        year = fm.get("year", "n.d.")
        title = fm.get("title", slug)
        if authors:
            first_last = str(authors[0]).split(",")[0].strip().split()[-1]
            if len(authors) > 2:
                short_author = f"{first_last} et al."
            elif len(authors) == 2:
                second_last = str(authors[1]).split(",")[0].strip().split()[-1]
                short_author = f"{first_last} & {second_last}"
            else:
                short_author = first_last
        else:
            short_author = "Unknown"
        cmap[slug] = f"{short_author} ({year})"
    return cmap


def _replace_wikilinks(text: str, citation_map: dict[str, str]) -> str:
    """Replace [[slug]] with (Author, Year) inline citations."""
    def _replacer(m):
        slug = m.group(1)
        if slug in citation_map:
            return citation_map[slug]
        # Keep concepts/patterns as readable names
        return slug.replace("_", " ")
    return _WIKILINK_RE.sub(_replacer, text)


def retrieve_wiki_context(queries: list[str], max_pages: int = 6) -> str:
    """Retrieve relevant wiki pages with proper academic citations."""
    seen_paths: set[str] = set()
    pages: list[str] = []
    all_source_slugs: set[str] = set()

    for q in queries:
        results = search_wiki(q, WIKI_DIR, max_results=3)
        for r in results:
            if r["path"] not in seen_paths and len(pages) < max_pages:
                seen_paths.add(r["path"])
                parts = r["path"].split("/")
                if len(parts) == 2:
                    subdir, name = parts[0], parts[1].replace(".md", "")
                    content = read_page(WIKI_DIR, subdir, name)
                    if content:
                        # Collect all source slugs referenced
                        for m in _WIKILINK_RE.finditer(content):
                            slug = m.group(1)
                            if _re.match(r"[a-z]+\d{4}_", slug):
                                all_source_slugs.add(slug)
                        pages.append(f"=== Wiki: {r['title']} ===\n{content}")

    if not pages:
        return ""

    # Build citation map and replace wiki-links
    citation_map = _build_citation_map(list(all_source_slugs))
    converted_pages = [_replace_wikilinks(p, citation_map) for p in pages]

    # Append bibliography
    if all_source_slugs:
        bib = get_bibliography(list(all_source_slugs), WIKI_DIR, None)
        converted_pages.append(bib)

    return "\n\n".join(converted_pages)


# ── condition runners ──────────────────────────────────────────────────

@dataclass
class RunResult:
    condition: str
    task_id: str
    response: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_s: float = 0.0
    search_calls: int = 0


def run_baseline(task: dict) -> RunResult:
    """Condition 1: model only, no tools or context."""
    t0 = time.time()
    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": (
                "You are an expert in computational biology, single-cell genomics, "
                "and multimodal AI. Answer accurately and cite specific methods, "
                "models, or papers when relevant. If you are unsure, say so."
            )},
            {"role": "user", "content": task["prompt"]},
        ],
    )
    latency = time.time() - t0
    return RunResult(
        condition="baseline",
        task_id=task["id"],
        response=resp.output_text,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        total_tokens=resp.usage.total_tokens,
        latency_s=latency,
    )


def run_wiki(task: dict) -> RunResult:
    """Condition 2: model + wiki context."""
    wiki_ctx = retrieve_wiki_context(task["wiki_queries"])
    t0 = time.time()
    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": (
                "You are an expert in computational biology, single-cell genomics, "
                "and multimodal AI. You have access to a curated research wiki below. "
                "Use it to ground your answer with specific findings, methods, and "
                "citations. If the wiki doesn't cover something, say so."
            )},
            {"role": "user", "content": (
                f"## Research Wiki Context\n\n{wiki_ctx}\n\n"
                f"---\n\n## Question\n\n{task['prompt']}"
            )},
        ],
    )
    latency = time.time() - t0
    return RunResult(
        condition="wiki",
        task_id=task["id"],
        response=resp.output_text,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        total_tokens=resp.usage.total_tokens,
        latency_s=latency,
    )


def run_agentic(task: dict) -> RunResult:
    """Condition 3: model + web_search tool."""
    t0 = time.time()
    resp = client.responses.create(
        model=MODEL,
        tools=[{"type": "web_search_preview", "search_context_size": SEARCH_CONTEXT_SIZE}],
        input=[
            {"role": "system", "content": (
                "You are an expert in computational biology, single-cell genomics, "
                "and multimodal AI. Use web search to find relevant papers, methods, "
                "and findings. Cite specific sources. If you are unsure, search for it."
            )},
            {"role": "user", "content": task["prompt"]},
        ],
    )
    latency = time.time() - t0
    # Count search calls
    search_calls = sum(
        1 for item in (resp.output or [])
        if getattr(item, 'type', '') == 'web_search_call'
    )
    return RunResult(
        condition="agentic",
        task_id=task["id"],
        response=resp.output_text,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        total_tokens=resp.usage.total_tokens,
        latency_s=latency,
        search_calls=search_calls,
    )


def run_agentic_wiki(task: dict) -> RunResult:
    """Condition 4: model + web_search + wiki context."""
    wiki_ctx = retrieve_wiki_context(task["wiki_queries"])
    t0 = time.time()
    resp = client.responses.create(
        model=MODEL,
        tools=[{"type": "web_search_preview", "search_context_size": SEARCH_CONTEXT_SIZE}],
        input=[
            {"role": "system", "content": (
                "You are an expert in computational biology, single-cell genomics, "
                "and multimodal AI. You have access to a curated research wiki AND "
                "web search. Use the wiki for grounded domain knowledge and web search "
                "for additional details. Cite specific sources."
            )},
            {"role": "user", "content": (
                f"## Research Wiki Context\n\n{wiki_ctx}\n\n"
                f"---\n\n## Question\n\n{task['prompt']}"
            )},
        ],
    )
    latency = time.time() - t0
    search_calls = sum(
        1 for item in (resp.output or [])
        if getattr(item, 'type', '') == 'web_search_call'
    )
    return RunResult(
        condition="agentic_wiki",
        task_id=task["id"],
        response=resp.output_text,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        total_tokens=resp.usage.total_tokens,
        latency_s=latency,
        search_calls=search_calls,
    )


# ── LLM judge ─────────────────────────────────────────────────────────

JUDGE_SYSTEM = """\
You are an expert evaluator for academic AI/biology research responses.
Score each response on the following dimensions (1-10 scale each):

1. **Accuracy** (1-10): Factual correctness. Are claims supported by real methods/papers?
   Deduct for fabricated citations, wrong numbers, or incorrect attributions.
2. **Completeness** (1-10): Does it cover the key aspects? (see gold concepts list)
3. **Specificity** (1-10): Does it cite specific models, papers, numbers, or methods
   rather than vague generalities?
4. **Hallucination** (1-10, where 10 = NO hallucination): Rate how free of fabricated
   facts, fake citations, or invented details the response is.
5. **Usefulness** (1-10): Would a researcher find this actionable and insightful?

Also provide:
- hallucination_details: List any specific hallucinated claims (empty list if none)
- gold_coverage: Which gold concepts were covered (list of indices, 0-based)

Return ONLY valid JSON with this schema:
{
  "accuracy": <int>,
  "completeness": <int>,
  "specificity": <int>,
  "hallucination_freedom": <int>,
  "usefulness": <int>,
  "hallucination_details": [<string>, ...],
  "gold_coverage": [<int>, ...],
  "reasoning": "<brief explanation>"
}
"""


def judge_response(task: dict, result: RunResult) -> dict:
    """Use GPT-5 to evaluate a response."""
    prompt = (
        f"## Task\nCategory: {task['category']}\n"
        f"Prompt: {task['prompt']}\n\n"
        f"## Gold Concepts (for completeness scoring)\n"
        + "\n".join(f"{i}. {c}" for i, c in enumerate(task["gold_concepts"]))
        + f"\n\n## Response to Evaluate\n{result.response}"
    )

    resp = client.responses.create(
        model=JUDGE,
        input=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        text={"format": {"type": "json_object"}},
    )

    try:
        scores = json.loads(resp.output_text)
    except json.JSONDecodeError:
        scores = {
            "accuracy": 0, "completeness": 0, "specificity": 0,
            "hallucination_freedom": 0, "usefulness": 0,
            "hallucination_details": ["PARSE_ERROR"],
            "gold_coverage": [],
            "reasoning": resp.output_text[:500],
        }

    scores["judge_input_tokens"] = resp.usage.input_tokens
    scores["judge_output_tokens"] = resp.usage.output_tokens
    return scores


# ── main ───────────────────────────────────────────────────────────────

CONDITIONS = {
    "baseline": run_baseline,
    "wiki": run_wiki,
    "agentic": run_agentic,
    "agentic_wiki": run_agentic_wiki,
}


def run_evaluation():
    all_results: list[dict] = []
    total = len(TASKS) * len(CONDITIONS)
    done = 0

    for task in TASKS:
        for cond_name, cond_fn in CONDITIONS.items():
            done += 1
            print(f"[{done}/{total}] {task['id']} / {cond_name} ...", flush=True)

            try:
                result = cond_fn(task)
            except Exception as e:
                print(f"  ERROR running: {e}")
                result = RunResult(
                    condition=cond_name,
                    task_id=task["id"],
                    response=f"ERROR: {e}",
                )

            # Judge
            try:
                scores = judge_response(task, result)
            except Exception as e:
                print(f"  ERROR judging: {e}")
                scores = {"error": str(e)}

            record = {
                "task_id": task["id"],
                "category": task["category"],
                "condition": cond_name,
                "response": result.response,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "latency_s": round(result.latency_s, 2),
                "search_calls": result.search_calls,
                **scores,
            }
            all_results.append(record)

            # Save incrementally
            out_path = RESULTS_DIR / "eval_results.json"
            with open(out_path, "w") as f:
                json.dump(all_results, f, indent=2)

            print(f"  done — quality={scores.get('accuracy','?')}/{scores.get('completeness','?')}/{scores.get('specificity','?')} "
                  f"halluc={scores.get('hallucination_freedom','?')} "
                  f"tokens={result.total_tokens} latency={result.latency_s:.1f}s")

    print(f"\nAll results saved to {out_path}")
    return all_results


if __name__ == "__main__":
    run_evaluation()
