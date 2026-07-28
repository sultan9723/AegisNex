from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelTier:
    name: str
    provider: str
    model: str
    input_cost_per_million: float
    output_cost_per_million: float


@dataclass(frozen=True)
class ComplexityResult:
    level: str
    score: int
    reasons: list[str]


@dataclass(frozen=True)
class RoutingDecision:
    requested_provider: str
    requested_model: str
    selected_tier: str
    selected_provider: str
    selected_model: str
    complexity: ComplexityResult
    routing_disabled: bool
    reason: str
    input_cost_per_million: float
    output_cost_per_million: float
    requested_input_cost_per_million: float
    requested_output_cost_per_million: float


DEFAULT_MODEL_TIERS: dict[str, ModelTier] = {
    "cheap": ModelTier("cheap", "openai", "gpt-4o-mini", 0.15, 0.60),
    "medium": ModelTier("medium", "openai", "gpt-4o", 2.50, 10.00),
    "frontier": ModelTier("frontier", "openai", "gpt-4.1", 2.00, 8.00),
}

MODEL_PRICE_HINTS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
}

FRONTIER_KEYWORDS = re.compile(
    r"\b(production|security|compliance|legal|incident|architecture|migration|"
    r"threat|vulnerability|root cause|financial|payment|deploy|rollback)\b",
    re.IGNORECASE,
)
MEDIUM_KEYWORDS = re.compile(
    r"\b(analyze|compare|summarize|debug|refactor|plan|strategy|policy|benchmark)\b",
    re.IGNORECASE,
)


def _coerce_tier(name: str, data: dict[str, Any]) -> ModelTier:
    fallback = DEFAULT_MODEL_TIERS[name]
    return ModelTier(
        name=name,
        provider=str(data.get("provider") or fallback.provider),
        model=str(data.get("model") or fallback.model),
        input_cost_per_million=float(
            data.get("input_cost_per_million", fallback.input_cost_per_million)
        ),
        output_cost_per_million=float(
            data.get("output_cost_per_million", fallback.output_cost_per_million)
        ),
    )


def load_model_tiers() -> dict[str, ModelTier]:
    raw = os.getenv("AEGIS_COMMANDMESH_MODEL_TIERS", "").strip()
    if not raw:
        return dict(DEFAULT_MODEL_TIERS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return dict(DEFAULT_MODEL_TIERS)
    if not isinstance(parsed, dict):
        return dict(DEFAULT_MODEL_TIERS)
    tiers = dict(DEFAULT_MODEL_TIERS)
    for name in ("cheap", "medium", "frontier"):
        value = parsed.get(name)
        if isinstance(value, dict):
            tiers[name] = _coerce_tier(name, value)
    return tiers


def classify_complexity(
    prompt_text: str,
    *,
    prompt_tokens: int,
    has_tools: bool = False,
    action_type: str = "chat_completion",
) -> ComplexityResult:
    score = 0
    reasons: list[str] = []
    if prompt_tokens > 2500:
        score += 70
        reasons.append("long_prompt")
    elif prompt_tokens > 800:
        score += 35
        reasons.append("medium_prompt")
    elif prompt_tokens < 200:
        score -= 10
        reasons.append("short_prompt")

    if has_tools:
        score += 35
        reasons.append("tool_calling")
    if FRONTIER_KEYWORDS.search(prompt_text):
        score += 40
        reasons.append("high_risk_keywords")
    elif MEDIUM_KEYWORDS.search(prompt_text):
        score += 20
        reasons.append("analysis_keywords")
    if action_type not in {"chat_completion", "query", "summarize"}:
        score += 15
        reasons.append("non_query_action")

    if score >= 65:
        level = "frontier"
    elif score >= 20:
        level = "medium"
    else:
        level = "cheap"
    return ComplexityResult(level=level, score=score, reasons=reasons or ["default"])


def _price_for_model(model: str, tiers: dict[str, ModelTier]) -> tuple[float, float]:
    normalized = model.strip().lower()
    for tier in tiers.values():
        if tier.model.lower() == normalized:
            return tier.input_cost_per_million, tier.output_cost_per_million
    return MODEL_PRICE_HINTS.get(
        normalized,
        (tiers["medium"].input_cost_per_million, tiers["medium"].output_cost_per_million),
    )


def estimate_cost_usd(
    input_tokens: int, output_tokens: int, input_per_million: float, output_per_million: float
) -> float:
    return round(
        (input_tokens / 1_000_000 * input_per_million)
        + (output_tokens / 1_000_000 * output_per_million),
        8,
    )


def decide_route(
    *,
    requested_provider: str,
    requested_model: str,
    prompt_text: str,
    prompt_tokens: int,
    has_tools: bool,
    metadata: dict[str, Any] | None = None,
) -> RoutingDecision:
    metadata = metadata or {}
    tiers = load_model_tiers()
    complexity = classify_complexity(prompt_text, prompt_tokens=prompt_tokens, has_tools=has_tools)
    routing_disabled = bool(metadata.get("routing_disabled") or metadata.get("model_locked"))
    if routing_disabled:
        selected_provider = requested_provider
        selected_model = requested_model or tiers[complexity.level].model
        selected_tier = "locked"
        reason = "caller_locked_model"
    else:
        tier = tiers[complexity.level]
        selected_provider = tier.provider
        selected_model = tier.model
        selected_tier = tier.name
        reason = f"complexity:{complexity.level}"

    selected_input, selected_output = _price_for_model(selected_model, tiers)
    requested_input, requested_output = _price_for_model(requested_model or selected_model, tiers)
    return RoutingDecision(
        requested_provider=requested_provider,
        requested_model=requested_model,
        selected_tier=selected_tier,
        selected_provider=selected_provider,
        selected_model=selected_model,
        complexity=complexity,
        routing_disabled=routing_disabled,
        reason=reason,
        input_cost_per_million=selected_input,
        output_cost_per_million=selected_output,
        requested_input_cost_per_million=requested_input,
        requested_output_cost_per_million=requested_output,
    )
