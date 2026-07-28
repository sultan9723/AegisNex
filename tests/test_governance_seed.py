from pathlib import Path

from src.ai_governance import ActionVerdict, GovernanceManager
from src.governance_seed import seed_governance


def test_seed_governance_populates_demo_policy_library(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "seed.db")

    counts = seed_governance(gov)

    assert counts["agents"] >= 15
    assert counts["policies"] >= 20
    assert counts["actions"] >= 25
    assert counts["anomalies"] >= 3

    policy_names = {policy.name for policy in gov.list_policies()}
    assert "customer-refund-approval-required" in policy_names
    assert "prod-deploy-approval-required" in policy_names
    assert "block-direct-prod-db-write" in policy_names
    assert "block-secret-exfiltration" in policy_names
    assert "global-registered-agent-default-allow" in policy_names

    built_in_ids = {"planner", "knowledge", "docker", "metrics", "policy", "risk", "verifier", "executor"}
    agents = {agent.agent_id: agent for agent in gov.list_agents() if agent.agent_id in built_in_ids}
    assert set(agents) == built_in_ids
    for agent in agents.values():
        data = agent.to_dict()
        assert data["provider"]
        assert data["model"]
        assert data["version"]
        assert data["department"]
        assert data["purpose"]
        assert isinstance(data["permissions"], list)
        assert isinstance(data["connected_tools"], list)
        assert isinstance(data["policies"], list)
        assert data["daily_budget"] > 0
        assert data["monthly_budget"] >= data["daily_budget"]
        assert data["execution_count"] >= 2
        assert gov.get_agent_history(agent.agent_id, limit=10)


def test_seeded_policies_enforce_allow_deny_and_approval(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "seed.db")
    seed_governance(gov)

    refund_verdict, refund_reason = gov.evaluate_policies(
        "customer-support-agent",
        "refund",
        "/api/billing/refunds/customer",
    )
    prod_db_verdict, prod_db_reason = gov.evaluate_policies(
        "deployment-agent",
        "write",
        "/api/prod/db/payments",
    )
    metrics_verdict, metrics_reason = gov.evaluate_policies(
        "monitoring-agent",
        "query",
        "/api/metrics",
    )

    assert refund_verdict == ActionVerdict.PENDING_APPROVAL.value
    assert refund_reason == "Requires approval per policy: customer-refund-approval-required"
    assert prod_db_verdict == ActionVerdict.DENIED.value
    assert prod_db_reason == "Denied by policy: block-direct-prod-db-write"
    assert metrics_verdict == ActionVerdict.ALLOWED.value
    assert metrics_reason == "Allowed by policy: monitoring-query-allowed"


def test_seed_governance_is_idempotent(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "seed.db")

    first = seed_governance(gov)
    second = seed_governance(gov)

    assert first["agents"] > 0
    assert first["policies"] > 0
    assert second == {"agents": 0, "policies": 0, "actions": 0, "anomalies": 0}
