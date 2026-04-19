"""GPT-5 and GPT-4.1 synthesis prompts for Phase 4 wiki page generation."""
from __future__ import annotations

# ─── Pattern clustering ────────────────────────────────────────────────────────

PATTERN_CLUSTER_SYSTEM = """\
You are grouping academic papers by their experimental design pattern.

You will receive:
1. A list of existing pattern pages (slug: title)
2. A list of papers, each with paper_id, title, and logic_pattern

logic_pattern is a free-text label like "premise → innovation → validation" or
"gap_analysis → novel_method → comparative_study". Different phrasings can describe
the same fundamental experimental approach.

Your task:
1. Group papers that follow the same fundamental experimental logic, even if worded differently.
2. Assign papers to existing pattern pages where the fit is strong.
3. Propose new pattern slugs for papers that don't fit existing pages — but ONLY if >=2 papers share the pattern.
4. Papers that don't cluster with at least one other paper go in "unassigned".

Return JSON exactly:
{
  "assignments": {
    "<pattern_slug>": ["paper_id_1", "paper_id_2"]
  },
  "new_pattern_titles": {
    "<new_slug>": "Human-readable title for new pattern"
  },
  "unassigned": ["paper_id_alone"]
}

Rules:
- Pattern slugs: lowercase, underscore-separated, <=5 words
- A paper appears in exactly one assignment or in unassigned — never both
- Only include assignments with >=2 papers; single-paper groups go to unassigned
"""

# ─── Concept page synthesis (GPT-5) ───────────────────────────────────────────

CONCEPT_SYNTHESIS_SYSTEM = """\
You are writing a wiki page for a scientific concept used by a research knowledge base.

You will receive:
1. The concept name and slug
2. The existing page content (if any) — use as context, not as content to preserve
3. All findings mapped to this concept from papers in the knowledge base
4. Research relationships involving this concept

Write a SYNTHESIZED NARRATIVE wiki page — like a mini-review by an expert who has read all the papers.
Do NOT list findings per paper. Instead, synthesize across papers.

The page MUST have this structure:

---
title: "{concept_title}"
type: concept
domain_tags: [<2-4 relevant scientific domain tags>]
source_papers: [<[[paper_slug]] for each contributing paper>]
last_updated: "{today}"
---

# {concept_title}

## State of the field
What does the research collectively show? What is established with confidence?

## Key findings
The most important results. Cite papers inline with [[paper_slug]].
Include quantitative results where available.

## Contradictions
Where do papers disagree? Present both sides with citations.
(Omit section if no contradictions exist.)

## Research trajectory
How has understanding evolved? What built on what?

## Open questions
What does the knowledge base not yet answer?

Rules:
- Use [[paper_slug]] for ALL paper citations (never author-year format)
- Use [[concept_slug]] for cross-references to other concept pages
- The page must contain knowledge that no single paper states — synthesis is the value
- Write in clear, precise scientific prose (not bullet points in Key findings)
- If the existing page contains validated synthesis, incorporate and extend it rather than ignoring it
"""

# ─── Design pattern page synthesis (GPT-5) ────────────────────────────────────

PATTERN_SYNTHESIS_SYSTEM = """\
You are writing a wiki page for a research design pattern used by a scientific knowledge base.

A design pattern is an abstract experimental logic that multiple papers implement concretely in different ways.

You will receive:
1. The pattern slug and title
2. The existing page content (if any)
3. Papers using this pattern: their logic_pattern, reasoning chain, experimental pipeline, controls

The page MUST have this structure:

---
title: "{pattern_title}"
type: pattern
confidence: high
domain_tags: [<2-4 relevant tags>]
papers_using: [<[[paper_slug]] for each paper>]
last_updated: "{today}"
---

# {pattern_title}

## What this pattern is
Define the abstract experimental logic in 2-3 sentences. What is the fundamental approach?

## When to use it
What scientific questions is this pattern suited for? What conditions make it appropriate?

## How papers implement it
For each paper, describe HOW they used this pattern — what made their implementation distinctive.
Use [[paper_slug]] citations.

## Common pitfalls
What can go wrong? What do the papers collectively reveal about failure modes?

Rules:
- Describe the ABSTRACT pattern, not just a list of paper summaries
- Use [[paper_slug]] for all citations
- Keep it practical — a researcher reading this should understand when and how to apply the pattern
"""

# ─── Writing style page synthesis (GPT-4.1) ───────────────────────────────────

STYLE_SYNTHESIS_SYSTEM = """\
You are writing a practical writing style guide for academic papers in a specific venue and topic area.

You will receive structured writing convention data extracted from multiple papers in this venue+topic group.

The page MUST have this structure:

---
title: "{style_title}"
type: writing_style
venue: "{venue}"
topic_tags: [<2-4 topic tags>]
papers_analyzed: [<[[paper_slug]] for each paper>]
last_updated: "{today}"
confidence: {confidence}
---

# {style_title}

## Structural conventions
- **Section order:** <typical order observed across papers>
- **Results placement:** <before or after methods>
- **Introduction strategy:** <how the intro is typically structured>
- **Discussion arc:** <how discussion typically flows>
- **Supplementary materials:** <how/whether extended data is used>

## Prose and tone
- **Voice:** <active/passive/mixed — cite specific patterns>
- **Tense discipline:** <how tense is used for different content types>
- **Sentence style:** <short declarative vs. explanatory; paragraph structure>
- **Hedging:** <level and specific verbatim phrases observed>
- **Transitions:** <verbatim transition phrases from the papers>
- **Quantitative reporting:** <how numbers and statistics are presented>

Rules:
- Include VERBATIM examples from the papers wherever relevant (in quotes)
- Be concrete and imitable — a researcher should be able to directly apply this guide
- Note variation across papers where it exists; don't force false uniformity
- Use [[paper_slug]] when attributing specific examples to specific papers
"""
