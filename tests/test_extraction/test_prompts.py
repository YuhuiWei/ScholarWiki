import pytest
from scholarwiki.extraction.prompts import (
    knowledge, roadmap, experiment, writing, logic
)

MODULES = [
    (knowledge, "knowledge"),
    (roadmap, "roadmap"),
    (experiment, "experiment"),
    (writing, "writing"),
    (logic, "logic"),
]


@pytest.mark.parametrize("module, expected_name", MODULES)
def test_module_name(module, expected_name):
    assert module.MODULE_NAME == expected_name


@pytest.mark.parametrize("module, _", MODULES)
def test_system_prompt_is_nonempty_string(module, _):
    assert isinstance(module.SYSTEM_PROMPT, str)
    assert len(module.SYSTEM_PROMPT) > 200


@pytest.mark.parametrize("module, _", MODULES)
def test_system_prompt_instructs_json_only(module, _):
    prompt_lower = module.SYSTEM_PROMPT.lower()
    assert "json" in prompt_lower


@pytest.mark.parametrize("module, _", MODULES)
def test_system_prompt_no_fstring_artifacts(module, _):
    # Prompts must be string constants, not accidentally broken f-strings
    assert "{paper_text}" not in module.SYSTEM_PROMPT
    assert "{text}" not in module.SYSTEM_PROMPT
