from src.commandmesh_routing import classify_complexity, decide_route, estimate_cost_usd


def test_classify_complexity_routes_short_plain_prompt_to_cheap() -> None:
    result = classify_complexity("Say hello", prompt_tokens=2)

    assert result.level == "cheap"
    assert "short_prompt" in result.reasons


def test_classify_complexity_routes_tool_and_production_prompt_to_frontier() -> None:
    result = classify_complexity(
        "Analyze this production deployment rollback risk",
        prompt_tokens=120,
        has_tools=True,
    )

    assert result.level == "frontier"
    assert "tool_calling" in result.reasons
    assert "high_risk_keywords" in result.reasons


def test_decide_route_downgrades_simple_requested_frontier_model() -> None:
    decision = decide_route(
        requested_provider="openai",
        requested_model="gpt-4.1",
        prompt_text="Summarize this short note",
        prompt_tokens=20,
        has_tools=False,
    )

    assert decision.selected_tier == "cheap"
    assert decision.selected_model == "gpt-4o-mini"
    assert decision.reason == "complexity:cheap"


def test_decide_route_respects_locked_model() -> None:
    decision = decide_route(
        requested_provider="openai",
        requested_model="gpt-4.1",
        prompt_text="Summarize this short note",
        prompt_tokens=20,
        has_tools=False,
        metadata={"model_locked": True},
    )

    assert decision.selected_tier == "locked"
    assert decision.selected_model == "gpt-4.1"
    assert decision.routing_disabled is True


def test_estimate_cost_usd_uses_million_token_rates() -> None:
    assert estimate_cost_usd(1000, 500, 1.00, 2.00) == 0.002
