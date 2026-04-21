"""GPT-5 and GPT-4.1 synthesis prompts for Phase 4 wiki page generation."""
from __future__ import annotations

# ─── Pattern clustering ────────────────────────────────────────────────────────

PATTERN_CLUSTER_SYSTEM = """\
You are grouping academic papers by their specific experimental methodology.

You will receive:
1. A list of existing pattern pages (slug: title)
2. A list of papers, each with paper_id, title, logic_pattern, key_experiment_summary, \
and methodological_tags

key_experiment_summary: ordered pipeline steps describing HOW the experiment was conducted.
methodological_tags: terms describing specific experimental techniques used.

Your task:
1. Group papers that use the SAME SPECIFIC EXPERIMENTAL APPROACH, regardless of research domain.
   Focus on the concrete method (e.g. "perturbation + transcriptomic readout", \
"held-out benchmark comparison", "multi-cohort replication + ablation", \
"synthetic dataset generation + cross-model evaluation").
2. Assign papers to existing pattern pages where the fit is strong (exact method match).
3. Propose new pattern slugs ONLY if >=2 papers share a specific methodology.
4. Papers without a matching group go in "unassigned".

Cluster by HOW the experiment is conducted, not WHAT domain it's in:
- Too abstract: "validation_study", "novel_method_benchmark", "problem_solving"
- Concrete: "perturbation_transcriptome_analysis", "multi_benchmark_ablation", \
"synthetic_data_comparative_evaluation"

Aim for 3-8 concrete clusters per run.

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
- Pattern slugs: lowercase, underscore-separated, <=5 words, describe the METHOD not the domain
- A paper appears in exactly one assignment or in unassigned — never both
- Only include assignments with >=2 papers; single-paper groups go to unassigned
"""

# ─── Connection block (shared across all synthesis prompts) ───────────────────

_CONNECTIONS_BLOCK = """\

CONNECTIONS

In addition to the page body, you MUST include a `connections` list in the YAML frontmatter. \
Each entry links THIS page to another page listed under "CONNECTABLE PAGES" in the WIKI INDEX.

connections:
  - target: "[[slug_of_concept_or_pattern_or_writing_page]]"
    edge_type: "<see types below>"
    via_paper: "[[paper_slug]]"
    description: "One sentence explaining the relationship."

Fields:
  target      — slug of a CONNECTABLE page (concept, pattern, or writing style only).
                NEVER use a source paper slug as a target.
  edge_type   — see edge types below.
  via_paper   — REQUIRED. The [[paper_slug]] whose findings ground this connection.
                Must be one of the source paper slugs listed in the WIKI INDEX.
  description — one sentence explaining the epistemic relationship.

Edge types — choose the most specific that applies:
  subtopic_of       — this concept is a specific instance of a broader concept
  enables           — understanding or mastering this is a prerequisite for the target
  is_application_of — this applies a general principle to a more specific context
  contributes_to    — findings or methods here directly inform understanding of the target
  contradicts       — evidence here conflicts with claims on the target page
  is_pattern_for    — (patterns only) this experimental design is the standard approach for that concept
  is_style_for      — (writing pages only) this style guide covers papers in that concept area
  related_to        — meaningful relationship that does not fit the types above (use sparingly)

Rules:
  - Generate 2–5 connections per page.
  - ONLY use slugs from "CONNECTABLE PAGES" as targets — never source paper slugs.
  - Every connection MUST include via_paper citing the source paper that justifies this link.
  - Prefer specific edge types over `related_to`.
  - A connection must represent a meaningful epistemic relationship —
    not merely that both topics share a broad domain.
  - Cross-type connections are encouraged: concept pages may link to pattern or \
writing pages, and vice versa.
"""

# ─── Concept page synthesis (GPT-5) ───────────────────────────────────────────

CONCEPT_SYNTHESIS_SYSTEM = """\
You are writing a wiki page for a scientific concept used by a research knowledge base.

You will receive:
1. The concept name and slug
2. The existing page content (if any) — use as context, not as content to preserve
3. All findings mapped to this concept from papers in the knowledge base
4. Research relationships involving this concept
5. A WIKI INDEX of pages you may link to

Write a SYNTHESIZED NARRATIVE wiki page — like a mini-review by an expert who has read all the papers.
Do NOT list findings per paper. Instead, synthesize across papers.

The page MUST have this structure:

---
title: "{concept_title}"
type: concept
domain_tags: [<2-4 relevant scientific domain tags>]
source_papers: [<[[paper_slug]] for each contributing paper>]
connections:
  - target: "[[slug]]"
    edge_type: "subtopic_of"
    via_paper: "[[paper_slug]]"
    description: "One sentence."
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
""" + _CONNECTIONS_BLOCK

# ─── Design pattern page synthesis (GPT-5) ────────────────────────────────────

PATTERN_SYNTHESIS_SYSTEM = """\
You are writing a wiki page for a specific experimental methodology used across multiple research papers.

A methodology pattern is a concrete experimental approach that researchers can recognize and apply, \
independent of research domain.

You will receive:
1. The pattern slug and title
2. The existing page content (if any)
3. Papers using this pattern: their experimental pipeline steps, controls, and logic pattern
4. A WIKI INDEX of pages you may link to

The page MUST have this structure:

---
title: "{pattern_title}"
type: pattern
confidence: high
method_tags: [<2-4 concrete method tags, e.g. perturbation, transcriptomics, ablation>]
papers_using: [<[[paper_slug]] for each paper>]
connections:
  - target: "[[slug]]"
    edge_type: "is_pattern_for"
    via_paper: "[[paper_slug]]"
    description: "One sentence."
last_updated: "{today}"
---

# {pattern_title}

## What this methodology is
Describe the concrete experimental approach in 2-4 sentences. Name the specific steps, \
instruments, or procedures that define it — not abstract logic.

## When researchers use this approach
What scientific questions require this methodology? What data or conditions make it appropriate? \
What does it enable that simpler approaches cannot?

## How each paper implements it
For each paper, describe the specific implementation choices: what they measured, how they \
controlled for confounders, what computational steps they used. Use [[paper_slug]] citations.
Show variation across implementations — what differs, what stays constant.

## Practical considerations
What reagents, compute, or data prerequisites does this approach require?
What sample sizes or replication levels are typical?
What controls are essential vs. optional?

## Known failure modes
What does this methodology reliably fail to detect or account for? \
What do the papers collectively reveal about its blind spots?

Rules:
- Be concrete and actionable — a researcher should know exactly what protocol to follow
- Use [[paper_slug]] for all paper citations
- Use [[concept_slug]] for cross-references to concept pages
- Name actual tools, assays, datasets, or models where the papers mention them
- Never describe the pattern as "problem → solution → validation" — describe the actual method
""" + _CONNECTIONS_BLOCK

# ─── Writing style page synthesis (GPT-4.1) ───────────────────────────────────

STYLE_SYNTHESIS_SYSTEM = """\
You are writing a practical writing reference card for researchers who want to write papers \
targeting a specific venue and topic area.

You will receive:
1. Structured writing data extracted from papers in this venue+topic group, \
including verbatim phrases, section orders, and hedging examples.
2. A WIKI INDEX of pages you may link to.

This page is a REFERENCE CARD — concrete, imitable, immediately actionable.

The page MUST have this structure:

---
title: "{style_title}"
type: writing_style
venue: "{venue}"
topic_tags: [<2-4 topic tags>]
papers_analyzed: [<[[paper_slug]] for each paper>]
connections:
  - target: "[[slug]]"
    edge_type: "is_style_for"
    via_paper: "[[paper_slug]]"
    description: "One sentence."
last_updated: "{today}"
confidence: {confidence}
---

# {style_title}

## Paper structure
- **Section order:** <exact typical order, e.g. "Abstract → Introduction → Results → Methods → Discussion">
- **Results vs. Methods placement:** <which comes first and why>
- **Introduction length:** <typical paragraph count and arc, e.g. "3-4 paragraphs: broad context → gap → contribution">
- **Discussion arc:** <how the discussion flows, e.g. "restate findings → mechanisms → limitations → future work">
- **Supplementary materials:** <what goes there and how it is referenced>

## Sentence-level writing conventions
- **Voice:** <active / passive / mixed — name which sections use which>
- **Tense discipline:** <e.g. "past tense for methods and results; present tense for claims and interpretation">
- **Claim strength:** <how bold vs. hedged the main claims are — cite verbatim examples>
- **Quantitative reporting:** <exact format used, e.g. "mean ± SD (n=3, p<0.05 by Student's t-test)">

## Verbatim phrase bank
Copy these directly when writing for this venue:

**Opening a results section:**
> "<verbatim example from a paper>"

**Introducing a figure:**
> "<verbatim example>"

**Hedging / uncertainty:**
> "<verbatim hedging phrase>"
> "<second example if available>"

**Transitions between sections:**
> "<verbatim transition>"

**Stating a limitation:**
> "<verbatim limitation phrase>"

## What distinguishes this venue's style
2-4 observations about what makes writing in this venue distinctive compared to the default \
academic style. Be specific — name the feature and give an example.

Rules:
- Every item in the phrase bank must be VERBATIM text from one of the analyzed papers
- Attribute specific phrases to papers with [[paper_slug]] in parentheses after the quote
- If papers disagree on a convention, say so explicitly ("[[paper_slug_a]] uses X; [[paper_slug_b]] uses Y")
- Skip any section where you have no concrete evidence — do not fabricate conventions
- confidence: high means >=2 papers; low means 1 paper (note this limitation)
""" + _CONNECTIONS_BLOCK
