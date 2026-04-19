from scholarwiki.models import PaperEntry

def test_paper_entry_has_failed_modules_default():
    entry = PaperEntry(paper_id="abc123", title="Test", source="nexus")
    assert entry.failed_modules == []

def test_paper_entry_failed_modules_roundtrip():
    entry = PaperEntry(paper_id="abc123", title="Test", source="nexus",
                       failed_modules=["knowledge", "writing"])
    data = entry.model_dump()
    restored = PaperEntry.model_validate(data)
    assert restored.failed_modules == ["knowledge", "writing"]


# Append to tests/test_extraction/test_models.py
import json
from scholarwiki.extraction.models import (
    KnowledgeOutput, RoadmapOutput, ExperimentOutput, WritingOutput, LogicOutput
)


def test_knowledge_output_parses_full():
    data = {
        "knowledge_items": [
            {
                "id": "k1",
                "claim": "Method X outperforms Y on benchmark Z",
                "evidence_type": "experimental",
                "confidence": "high",
                "supporting_data": "Fig 3",
                "domain_tags": ["machine learning", "benchmark"],
                "related_concepts": ["transfer learning", "fine-tuning"],
                "quantitative_result": "5% improvement in AUC"
            }
        ]
    }
    out = KnowledgeOutput.model_validate(data)
    assert len(out.knowledge_items) == 1
    assert out.knowledge_items[0].claim == "Method X outperforms Y on benchmark Z"


def test_knowledge_output_tolerates_extra_fields():
    data = {"knowledge_items": [], "unexpected_field": "ignored"}
    out = KnowledgeOutput.model_validate(data)
    assert out.knowledge_items == []


def test_knowledge_output_tolerates_missing_optional():
    data = {"knowledge_items": [{"claim": "Only claim present"}]}
    out = KnowledgeOutput.model_validate(data)
    assert out.knowledge_items[0].confidence is None
    assert out.knowledge_items[0].domain_tags == []


def test_roadmap_output_parses():
    data = {
        "relationships": [
            {
                "relationship_type": "extends",
                "target_entity": "scVI (Lopez et al., 2018)",
                "target_doi": "10.1038/s41592-018-0229-2",
                "description": "Extends scVI VAE with supervision",
                "significance": "high"
            }
        ],
        "positioned_as": "Incremental improvement",
        "gap_filled": "No prior method handled both supervised and unsupervised",
        "field_context": "Part of deep learning wave for scRNA-seq"
    }
    out = RoadmapOutput.model_validate(data)
    assert len(out.relationships) == 1
    assert out.relationships[0].relationship_type == "extends"


def test_roadmap_output_empty_is_valid():
    out = RoadmapOutput.model_validate({})
    assert out.relationships == []
    assert out.positioned_as is None


def test_experiment_output_parses():
    data = {
        "datasets": [{"name": "PBMC 10x", "size": "68K cells", "role": "benchmark"}],
        "experimental_pipeline": [
            {"step": 1, "action": "QC filtering", "rationale": "Remove low quality cells", "tools": ["scanpy"]}
        ],
        "controls": [{"description": "5 baseline methods", "purpose": "Show improvement"}],
        "evaluation_metrics": [{"metric": "ARI", "purpose": "Cluster agreement"}],
        "key_parameters": {"latent_dims": 128},
        "reproducibility_notes": "Code at github.com/example"
    }
    out = ExperimentOutput.model_validate(data)
    assert out.datasets[0].name == "PBMC 10x"
    assert out.experimental_pipeline[0].action == "QC filtering"


def test_writing_output_parses():
    data = {
        "venue": "Nature Methods",
        "venue_type": "journal",
        "topic_area": "scRNA-seq integration",
        "figure_count": 6,
        "language_patterns": {
            "voice": "active in Results",
            "tense": "past for own results",
            "transition_phrases": ["Consistent with this finding..."],
            "common_phrases_by_context": {"introducing_result": "To determine whether..."}
        }
    }
    out = WritingOutput.model_validate(data)
    assert out.venue == "Nature Methods"
    assert out.language_patterns.transition_phrases == ["Consistent with this finding..."]


def test_logic_output_parses():
    data = {
        "hypothesis": "A supervised VAE corrects batch effects",
        "reasoning_chain": [
            {"step": 1, "type": "premise", "content": "Unsupervised methods fail when batch correlates with biology"}
        ],
        "logic_pattern": "problem_demonstration → innovation → benchmark",
        "assumptions": ["Labels are partially available"],
        "limitations_acknowledged": ["Only tested on droplet-based protocols"],
        "strengths_of_argument": ["Multiple independent datasets"]
    }
    out = LogicOutput.model_validate(data)
    assert out.hypothesis == "A supervised VAE corrects batch effects"
    assert out.reasoning_chain[0].type == "premise"


def test_all_models_tolerate_empty_dict():
    for cls in [KnowledgeOutput, RoadmapOutput, ExperimentOutput, WritingOutput, LogicOutput]:
        obj = cls.model_validate({})
        assert obj is not None
