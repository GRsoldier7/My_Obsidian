"""
tests/test_openrouter_cascade.py
Tests for the OpenRouter model cascade logic in tools/process_brain_dump.py.

Verifies:
- Models are tried in order (gemma → llama → nemotron)
- Second model is tried when first fails
- All-fail scenario returns None (triggers regex fallback)
- Valid task lines are returned unchanged
- NONE response is treated as empty result
"""
import sys
import os
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from process_brain_dump import (
    EXTRACT_MODELS,
    _chat_with_fallback,
    extract_tasks_from_section,
    extract_notes_from_section,
    extract_articles_from_section,
)
from conftest import make_openrouter_response


# ── _chat_with_fallback ───────────────────────────────────────────────────────

def test_cascade_first_model_succeeds():
    """When gemma succeeds, llama and nemotron are never called."""
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response("some output")

    result = _chat_with_fallback(client, "test prompt")

    assert result == "some output"
    assert client.chat.completions.create.call_count == 1
    # First call must use the first model
    first_call_model = client.chat.completions.create.call_args_list[0].kwargs.get(
        "model"
    ) or client.chat.completions.create.call_args_list[0].args[0] if client.chat.completions.create.call_args_list[0].args else client.chat.completions.create.call_args_list[0][1].get("model")
    assert first_call_model == EXTRACT_MODELS[0]


def test_cascade_first_fails_second_succeeds():
    """When gemma fails, llama is tried and succeeds."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        Exception("Rate limit"),
        make_openrouter_response("task from llama"),
    ]

    result = _chat_with_fallback(client, "test prompt")

    assert result == "task from llama"
    assert client.chat.completions.create.call_count == 2


def test_cascade_first_two_fail_third_succeeds():
    """Gemma and llama both fail — nemotron is the last chance."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        Exception("Rate limit"),
        Exception("Service unavailable"),
        make_openrouter_response("task from nemotron"),
    ]

    result = _chat_with_fallback(client, "test prompt")

    assert result == "task from nemotron"
    assert client.chat.completions.create.call_count == 3


def test_cascade_all_models_fail_returns_none():
    """When all 3 models fail, _chat_with_fallback returns None."""
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("All down")

    result = _chat_with_fallback(client, "test prompt")

    assert result is None
    assert client.chat.completions.create.call_count == len(EXTRACT_MODELS)


def test_cascade_tries_all_defined_models():
    """The cascade tries exactly the models defined in EXTRACT_MODELS."""
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("fail")

    _chat_with_fallback(client, "test prompt")

    called_models = [
        call_args.kwargs.get("model", call_args.args[0] if call_args.args else None)
        for call_args in client.chat.completions.create.call_args_list
    ]
    # All models in EXTRACT_MODELS should have been called
    for model in EXTRACT_MODELS:
        assert model in called_models, f"Model {model} was never tried"


def test_cascade_empty_response_tries_next():
    """Empty string response is treated as failure — next model is tried."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        make_openrouter_response(""),   # empty response
        make_openrouter_response("valid output"),
    ]

    result = _chat_with_fallback(client, "test prompt")

    assert result == "valid output"
    assert client.chat.completions.create.call_count == 2


# ── extract_tasks_from_section ────────────────────────────────────────────────

def test_extract_tasks_returns_valid_format(mock_openrouter_success):
    """extract_tasks_from_section returns task lines starting with '- [ ]'."""
    tasks = extract_tasks_from_section(
        mock_openrouter_success,
        "✅ To Do's",
        "- Call Dr. Smith about hip MRI",
        "health",
        "2026-04-08",
    )

    assert len(tasks) > 0
    for task in tasks:
        assert task.startswith("- [ ]"), f"Task missing checkbox: {task!r}"
        assert "[area::" in task, f"Task missing area tag: {task!r}"


def test_extract_tasks_none_response_returns_empty(mock_openrouter_none_response):
    """NONE response from OpenRouter → empty list (no junk tasks created)."""
    tasks = extract_tasks_from_section(
        mock_openrouter_none_response,
        "✅ To Do's",
        "Some vague content with no actionable items",
        "personal",
        "2026-04-08",
    )

    assert tasks == []


def test_extract_tasks_all_fail_returns_empty(mock_openrouter_all_fail):
    """All models failing → empty list (graceful degradation)."""
    tasks = extract_tasks_from_section(
        mock_openrouter_all_fail,
        "✅ To Do's",
        "Buy milk",
        "personal",
        "2026-04-08",
    )

    assert tasks == []


def test_extract_tasks_filters_non_task_lines():
    """Only lines starting with '- [ ]' are returned — no prose lines."""
    client = MagicMock()
    # Response contains a mix of tasks and prose
    client.chat.completions.create.return_value = make_openrouter_response(
        "Here are the tasks I found:\n"
        "- [ ] Valid task [area:: personal] [priority:: B]\n"
        "This is a summary line\n"
        "- [ ] Another task [area:: work] [priority:: A]\n"
    )

    tasks = extract_tasks_from_section(client, "Notes", "content", "personal", "2026-04-08")

    assert len(tasks) == 2
    assert all(t.startswith("- [ ]") for t in tasks)


# ── extract_notes_from_section ────────────────────────────────────────────────

def test_extract_notes_returns_valid_json_objects():
    """Notes extraction returns list of dicts with title/content/area."""
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response(
        '{"title": "Habit tracker idea", "content": "Integrate with Obsidian via NLP", "area": "personal"}\n'
        '{"title": "Biohacking note", "content": "Look into peptides for recovery", "area": "health"}'
    )

    notes = extract_notes_from_section(client, "💡 Ideas", "content", "personal", "2026-04-08")

    assert len(notes) == 2
    assert notes[0]["title"] == "Habit tracker idea"
    assert notes[0]["area"] == "personal"


def test_extract_notes_none_response_returns_empty():
    """NONE response → empty list."""
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response("NONE")

    notes = extract_notes_from_section(client, "💡 Ideas", "empty", "personal", "2026-04-08")

    assert notes == []


def test_extract_notes_malformed_json_skipped():
    """Lines that aren't valid JSON are silently skipped."""
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response(
        "not json at all\n"
        '{"title": "Valid note", "content": "content here", "area": "personal"}\n'
        "{broken json}"
    )

    notes = extract_notes_from_section(client, "Notes", "content", "personal", "2026-04-08")

    assert len(notes) == 1
    assert notes[0]["title"] == "Valid note"


# ── extract_articles_from_section ─────────────────────────────────────────────

def test_extract_articles_returns_markdown_links():
    """Articles extraction returns markdown link lines."""
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response(
        "- [AI Research Article](https://example.com/ai) — interesting read\n"
        "- [Biohacking Guide](https://example.com/bio) — peptide protocols"
    )

    articles = extract_articles_from_section(client, "article content", "personal", "2026-04-08")

    assert len(articles) == 2
    assert all(a.startswith("- [") for a in articles)


def test_extract_articles_none_returns_empty():
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response("NONE")

    articles = extract_articles_from_section(client, "no urls here", "personal", "2026-04-08")

    assert articles == []
