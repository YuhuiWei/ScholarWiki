# src/scholarwiki/extraction/models.py
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Module 1: Knowledge
# ---------------------------------------------------------------------------

class KnowledgeItem(_Base):
    id: Optional[str] = None
    claim: str
    evidence_type: Optional[str] = None   # experimental | computational | theoretical | review
    confidence: Optional[str] = None      # high | medium | low
    supporting_data: Optional[str] = None
    domain_tags: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    quantitative_result: Optional[str] = None


class KnowledgeOutput(_Base):
    knowledge_items: list[KnowledgeItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Module 2: Roadmap
# ---------------------------------------------------------------------------

class Relationship(_Base):
    relationship_type: str
    target_entity: str
    target_doi: Optional[str] = None
    target_arxiv_id: Optional[str] = None
    description: Optional[str] = None
    significance: Optional[str] = None   # high | medium | low


class RoadmapOutput(_Base):
    relationships: list[Relationship] = Field(default_factory=list)
    positioned_as: Optional[str] = None
    gap_filled: Optional[str] = None
    field_context: Optional[str] = None


# ---------------------------------------------------------------------------
# Module 3: Experiment
# ---------------------------------------------------------------------------

class Dataset(_Base):
    name: str
    size: Optional[str] = None
    source: Optional[str] = None
    accession: Optional[str] = None
    role: Optional[str] = None


class PipelineStep(_Base):
    step: Optional[int] = None
    action: str
    details: Optional[str] = None
    rationale: Optional[str] = None
    tools: list[str] = Field(default_factory=list)


class Control(_Base):
    control_type: Optional[str] = None
    description: str
    purpose: Optional[str] = None


class EvaluationMetric(_Base):
    metric: str
    purpose: Optional[str] = None
    threshold: Optional[str] = None


class ExperimentOutput(_Base):
    datasets: list[Dataset] = Field(default_factory=list)
    experimental_pipeline: list[PipelineStep] = Field(default_factory=list)
    controls: list[Control] = Field(default_factory=list)
    evaluation_metrics: list[EvaluationMetric] = Field(default_factory=list)
    key_parameters: dict[str, Any] = Field(default_factory=dict)
    reproducibility_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Module 4: Writing
# ---------------------------------------------------------------------------

class WritingStructure(_Base):
    section_order: list[str] = Field(default_factory=list)
    results_before_methods: Optional[bool] = None
    separate_methods: Optional[bool] = None
    supplementary_materials: Optional[bool] = None


class IntroductionPattern(_Base):
    paragraphs: Optional[int] = None
    strategy: Optional[str] = None
    how_gap_introduced: Optional[str] = None


class ResultsPattern(_Base):
    subsection_style: Optional[str] = None
    example_headers: list[str] = Field(default_factory=list)
    figure_reference_style: Optional[str] = None
    quantitative_reporting: Optional[str] = None


class DiscussionPattern(_Base):
    opening: Optional[str] = None
    structure: Optional[str] = None
    hedging_level: Optional[str] = None
    hedging_examples: list[str] = Field(default_factory=list)


class LanguagePatterns(_Base):
    voice: Optional[str] = None
    tense: Optional[str] = None
    transition_phrases: list[str] = Field(default_factory=list)
    common_phrases_by_context: dict[str, str] = Field(default_factory=dict)


class WritingOutput(_Base):
    venue: Optional[str] = None
    venue_type: Optional[str] = None
    topic_area: Optional[str] = None
    word_count_estimate: Optional[int] = None
    figure_count: Optional[int] = None
    extended_data_figures: Optional[int] = None
    structure: Optional[WritingStructure] = None
    introduction_pattern: Optional[IntroductionPattern] = None
    results_pattern: Optional[ResultsPattern] = None
    discussion_pattern: Optional[DiscussionPattern] = None
    language_patterns: Optional[LanguagePatterns] = None
    citation_style: Optional[str] = None
    data_availability: Optional[str] = None


# ---------------------------------------------------------------------------
# Module 5: Logic
# ---------------------------------------------------------------------------

class ReasoningStep(_Base):
    step: Optional[int] = None
    type: Optional[str] = None   # premise | problem_demonstration | innovation |
                                 # validation | ablation | extension | conclusion
    content: str
    evidence_basis: Optional[str] = None


class LogicOutput(_Base):
    hypothesis: Optional[str] = None
    reasoning_chain: list[ReasoningStep] = Field(default_factory=list)
    logic_pattern: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    limitations_acknowledged: list[str] = Field(default_factory=list)
    strengths_of_argument: list[str] = Field(default_factory=list)
