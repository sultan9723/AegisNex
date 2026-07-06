"""Tests for the Intelligence Engine pipeline: nodes, graph execution, and error handling."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

import pytest

from src.intelligence.nodes import (
    rag_generator_node,
    goal_evaluator_node,
    plan_node,
)
from src.intelligence.state import initial_state
from src.intelligence.providers.base import Message, ModelProvider, ProviderConfig


class MockProvider(ModelProvider):
    def __init__(self, responses: List[str] | None = None) -> None:
        super().__init__(ProviderConfig())
        self._responses = responses or ["Mock AI response"]
        self._call_index = 0

    def chat(self, messages: List[Message], **kwargs: Any) -> Message:
        resp = self._responses[self._call_index % len(self._responses)]
        self._call_index += 1
        return Message(role="assistant", content=resp)

    def chat_with_tools(self, messages: List[Message], tools: List[Dict[str, Any]], **kwargs: Any) -> Message:
        return self.chat(messages, **kwargs)

    def embed(self, text: str, **kwargs: Any) -> List[float]:
        return [0.1, 0.2, 0.3]

    @property
    def provider_name(self) -> str:
        return "mock"


# ─── rag_generator_node tests ────────────────────────────────────────────────

# rag_generator_node calls _get_rag_engine() which internally calls _get_provider()
# to obtain the provider. We patch _get_provider to control what the RAG engine uses.


@patch("src.intelligence.nodes._get_provider")
def test_rag_generator_with_provider(mock_get_provider):
    """Given a provider and tool results, rag_generator_node should set final_answer."""
    mock_provider = MockProvider(["LLM answer from RAG context"])
    mock_get_provider.return_value = mock_provider
    state = initial_state("check system health")
    state["provider"] = mock_provider
    state["tool_results"] = {"health": {"status": "ok", "count": 3}}
    state["retrieved_context"] = "All systems operational"

    result = rag_generator_node(state)

    assert result["final_answer"] == "LLM answer from RAG context"
    assert result["reasoning_summary"] == "LLM answer from RAG context"


def test_rag_generator_no_provider():
    """Without a provider in state, rag_generator_node should pass through."""
    state = initial_state("test request")
    state["tool_results"] = {"health": {"status": "ok"}}

    result = rag_generator_node(state)

    assert result["final_answer"] == ""
    assert result["reasoning_summary"] == ""


def test_rag_generator_no_tool_results():
    """Without tool_results, rag_generator_node should pass through even with provider."""
    mock_provider = MockProvider()
    state = initial_state("test request")
    state["provider"] = mock_provider

    result = rag_generator_node(state)

    assert result["final_answer"] == ""


@patch("src.intelligence.nodes._get_provider")
def test_rag_generator_provider_fallback_on_error(mock_get_provider):
    """When the provider raises, generate_with_context catches it and returns a fallback answer."""

    class FailingProvider(ModelProvider):
        def __init__(self) -> None:
            super().__init__(ProviderConfig())

        def chat(self, messages: List[Message], **kwargs: Any) -> Message:
            raise RuntimeError("API failure")

        def chat_with_tools(self, messages: List[Message], tools: List[Dict[str, Any]], **kwargs: Any) -> Message:
            raise RuntimeError("API failure")

        def embed(self, text: str, **kwargs: Any) -> List[float]:
            return []

        @property
        def provider_name(self) -> str:
            return "failing"

    mock_get_provider.return_value = FailingProvider()
    state = initial_state("test request")
    state["provider"] = FailingProvider()
    state["tool_results"] = {"docker": {"status": "ok"}}

    result = rag_generator_node(state)

    # The exception is caught by generate_with_context, which returns a fallback answer
    assert result["final_answer"] != ""
    assert "Based on available operational data" in result["final_answer"]
    assert "docker" in result["final_answer"]


# ─── goal_evaluator_node tests ───────────────────────────────────────────────


def test_goal_evaluator_preserves_existing_answer():
    """goal_evaluator_node should NOT overwrite final_answer when rag_generator already set it."""
    state = initial_state("analyze incidents")
    state["objective"] = "Incident analysis"
    state["tool_results"] = {
        "incident": {"status": "ok", "count": 5},
    }
    state["confidence"] = 0.85
    state["final_answer"] = "## LLM Analysis\n\nIncident #42 was caused by memory exhaustion."
    state["reasoning_summary"] = "Reasoning from LLM"

    result = goal_evaluator_node(state)

    assert result["goal_achieved"] is True
    assert "Incident #42 was caused by memory exhaustion." in result["final_answer"]
    assert result["final_answer"].startswith("## LLM Analysis")


def test_goal_evaluator_generates_answer_when_missing():
    """When no existing answer exists, goal_evaluator_node builds the template answer."""
    state = initial_state("check health")
    state["objective"] = "Health check"
    state["tool_results"] = {
        "health": {"status": "ok", "count": 3},
    }
    state["confidence"] = 0.7

    result = goal_evaluator_node(state)

    assert result["goal_achieved"] is True
    assert result["final_answer"] != ""
    assert "Analysis Summary" in result["final_answer"]
    assert "health" in result["final_answer"]


def test_goal_evaluator_preserves_answer_and_appends_metadata():
    """Existing answer is preserved, and metadata blocks (Observations, Errors) are appended."""
    state = initial_state("test")
    state["objective"] = "Test"
    state["tool_results"] = {"docker": {"status": "ok", "count": 2}}
    state["confidence"] = 0.65
    state["final_answer"] = "Initial LLM analysis here."
    state["observations"] = ["Container nginx is running"]
    state["errors"] = []

    result = goal_evaluator_node(state)

    assert "Initial LLM analysis here." in result["final_answer"]
    assert "Container nginx is running" in result["final_answer"]


def test_goal_evaluator_low_confidence():
    """Low confidence should flag manual investigation."""
    state = initial_state("test")
    state["objective"] = "Test"
    state["tool_results"] = {"health": {"status": "ok", "count": 1}}
    state["confidence"] = 0.2

    result = goal_evaluator_node(state)

    assert "Manual investigation recommended" in result["final_answer"]



# ─── plan_node with LLM ──────────────────────────────────────────────────────


def test_plan_node_falls_back_without_provider():
    """plan_node should use keyword matching when no provider is available."""
    state = initial_state("show me active incidents")

    result = plan_node(state)

    assert result["objective"] != ""
    assert len(result["current_plan"]) > 0


def test_plan_node_uses_llm_when_provider_available():
    """plan_node should call the LLM provider when one is in state."""
    mock_provider = MockProvider(['["incident", "audit"]'])
    state = initial_state("what happened with incidents today")
    state["provider"] = mock_provider

    result = plan_node(state)

    assert result["objective"] != ""
    assert len(result["current_plan"]) > 0


def test_plan_node_llm_fallback_on_json_error():
    """When LLM returns invalid JSON, plan_node falls back to keyword matching."""
    mock_provider = MockProvider(["not valid json at all"])
    state = initial_state("check system health")
    state["provider"] = mock_provider

    result = plan_node(state)

    assert result["objective"] != ""
    assert len(result["current_plan"]) > 0


# ─── run_workflow error handling ────────────────────────────────────────────


def test_run_workflow_handles_create_provider_failure():
    """run_workflow should not crash when create_provider raises."""
    from src.intelligence.graph import run_workflow, reset_graph
    reset_graph()

    with patch("src.intelligence.providers.factory.create_provider") as mock:
        mock.side_effect = RuntimeError("No API key configured")
        result = run_workflow("test system health")

    assert isinstance(result, dict)
    assert "execution_duration_ms" in result
    assert result.get("provider_used") == "openai"


def test_run_workflow_returns_dict_with_expected_keys():
    """run_workflow should return a dict with standard keys even without a provider."""
    from src.intelligence.graph import run_workflow, reset_graph
    reset_graph()

    with patch("src.intelligence.providers.factory.create_provider", return_value=None):
        result = run_workflow("check docker containers")

    assert isinstance(result, dict)
    assert "final_answer" in result
    assert "goal_achieved" in result
    assert "confidence" in result
    assert "execution_duration_ms" in result
    assert "executed_steps" in result
