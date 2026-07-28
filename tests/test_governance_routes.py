from pathlib import Path

from fastapi.testclient import TestClient

from src.ai_governance import AIAgent, AgentAction, AgentPolicy, GovernanceManager
from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.platform_db import PlatformRepository

from tests.test_dashboard import build_services


def _build_governance_app(tmp_path: Path):
    services = build_services(tmp_path)
    services.platform_repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    services.monitoring_engine = None
    auth_manager = AuthManager(
        UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    app = create_app(services, auth_manager=auth_manager, telemetry_db_path=str(tmp_path / "telemetry.db"))
    app.state.governance = GovernanceManager(tmp_path / "governance.db")
    return app, auth_manager


def _agent(agent_id: str, name: str) -> AIAgent:
    return AIAgent(
        agent_id=agent_id,
        name=name,
        agent_type="test",
        description="Route test agent",
        owner="platform",
        team="qa",
    )


def test_governance_routes_filter_agents_by_user_tenant(tmp_path: Path) -> None:
    app, auth_manager = _build_governance_app(tmp_path)
    org_one = app.state.tenant_manager.create_organization("Org One")
    org_two = app.state.tenant_manager.create_organization("Org Two")
    user_one = auth_manager.user_store.create_user("one@example.com", "password12345", role="administrator")
    user_two = auth_manager.user_store.create_user("two@example.com", "password12345", role="administrator")
    app.state.tenant_manager.assign_user_to_org(user_one.id, org_one.id, role="administrator")
    app.state.tenant_manager.assign_user_to_org(user_two.id, org_two.id, role="administrator")
    app.state.governance.register_agent(_agent("shared-agent", "Org One Agent"), tenant_id=f"org:{org_one.id}")
    app.state.governance.register_agent(_agent("shared-agent", "Org Two Agent"), tenant_id=f"org:{org_two.id}")

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        token_one = auth_manager.create_access_token(user_one)
        token_two = auth_manager.create_access_token(user_two)

        org_one_response = client.get("/api/governance/agents", cookies={"aegisnex_session": token_one})
        org_two_response = client.get("/api/governance/agents", cookies={"aegisnex_session": token_two})

    assert org_one_response.status_code == 200
    assert org_two_response.status_code == 200
    assert [agent["name"] for agent in org_one_response.json()["agents"]] == ["Org One Agent"]
    assert [agent["name"] for agent in org_two_response.json()["agents"]] == ["Org Two Agent"]


def test_governance_policy_routes_are_tenant_scoped(tmp_path: Path) -> None:
    app, auth_manager = _build_governance_app(tmp_path)
    org_one = app.state.tenant_manager.create_organization("Policy Org One")
    org_two = app.state.tenant_manager.create_organization("Policy Org Two")
    user_one = auth_manager.user_store.create_user("policy-one@example.com", "password12345", role="administrator")
    user_two = auth_manager.user_store.create_user("policy-two@example.com", "password12345", role="administrator")
    app.state.tenant_manager.assign_user_to_org(user_one.id, org_one.id, role="administrator")
    app.state.tenant_manager.assign_user_to_org(user_two.id, org_two.id, role="administrator")
    app.state.governance.register_agent(_agent("support-agent", "Support One"), tenant_id=f"org:{org_one.id}")
    app.state.governance.register_agent(_agent("support-agent", "Support Two"), tenant_id=f"org:{org_two.id}")

    payload_one = {
        "name": "refund-review",
        "description": "Org one refunds require approval",
        "policy_type": "approval",
        "target_agents": ["support-agent"],
        "conditions": {"action_type": "refund"},
        "effect": "approve",
        "priority": 10,
    }
    payload_two = {**payload_one, "description": "Org two refunds are blocked", "effect": "deny"}

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        token_one = auth_manager.create_access_token(user_one)
        token_two = auth_manager.create_access_token(user_two)
        cookies_one = {"aegisnex_session": token_one}
        cookies_two = {"aegisnex_session": token_two}

        create_one = client.post("/api/governance/policies", json=payload_one, cookies=cookies_one)
        create_two = client.post("/api/governance/policies", json=payload_two, cookies=cookies_two)
        list_one = client.get("/api/governance/policies", cookies=cookies_one)
        list_two = client.get("/api/governance/policies", cookies=cookies_two)
        eval_one = client.post(
            "/api/governance/evaluate",
            json={"agent_id": "support-agent", "action_type": "refund", "target": "/api/billing/refunds"},
            cookies=cookies_one,
        )
        eval_two = client.post(
            "/api/governance/evaluate",
            json={"agent_id": "support-agent", "action_type": "refund", "target": "/api/billing/refunds"},
            cookies=cookies_two,
        )

    assert create_one.status_code == 200
    assert create_two.status_code == 200
    assert list_one.json()["policies"][0]["description"] == "Org one refunds require approval"
    assert list_two.json()["policies"][0]["description"] == "Org two refunds are blocked"
    assert eval_one.json()["verdict"] == "pending_approval"
    assert eval_two.json()["verdict"] == "denied"


def test_agent_registry_detail_endpoints_return_enterprise_data(tmp_path: Path) -> None:
    app, auth_manager = _build_governance_app(tmp_path)
    user = auth_manager.user_store.create_user("registry@example.com", "password12345", role="administrator")
    app.state.governance.register_agent(
        AIAgent(
            agent_id="planner",
            name="Planner",
            agent_type="planning",
            description="Builds execution plans",
            owner="AI Platform",
            team="intelligence",
            department="AI Platform",
            purpose="Plan multi-step work",
            provider="openai",
            model="gpt-4o",
            version="2.3.0",
            daily_budget=45.0,
            monthly_budget=1200.0,
            average_cost=0.018,
            average_latency=1180.0,
            success_rate=96.4,
            permissions='["plan:create", "context:read"]',
            connected_tools='["rag_search", "tool_router"]',
            policies='["planner-default-allow"]',
            approval_required=False,
            allowed_tools='["rag_search", "tool_router"]',
            allowed_resources='["/api/ai/plan"]',
        )
    )
    app.state.governance.create_policy(
        AgentPolicy(
            policy_id=0,
            name="planner-default-allow",
            description="Planner can create plans",
            policy_type="access_control",
            target_agents='["planner"]',
            conditions='{"action_type": "plan"}',
            effect="allow",
            priority=10,
        )
    )
    app.state.governance.record_action(
        AgentAction(
            action_id="planner-history-1",
            agent_id="planner",
            action_type="plan",
            action_summary="Built an incident response plan",
            target_resource="/api/ai/plan",
            confidence_score=0.95,
            policy_verdict="allowed",
            status="success",
            duration_ms=1200,
        )
    )

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        token = auth_manager.create_access_token(user)
        cookies = {"aegisnex_session": token}

        list_response = client.get("/api/governance/agents", cookies=cookies)
        detail_response = client.get("/api/governance/agents/planner", cookies=cookies)
        history_response = client.get("/api/governance/agents/planner/history", cookies=cookies)
        policies_response = client.get("/api/governance/agents/planner/policies", cookies=cookies)
        tools_response = client.get("/api/governance/agents/planner/tools", cookies=cookies)
        metrics_response = client.get("/api/governance/agents/planner/metrics", cookies=cookies)
        missing_response = client.get("/api/governance/agents/missing/metrics", cookies=cookies)

    assert list_response.status_code == 200
    listed = list_response.json()["agents"][0]
    assert listed["id"] == "planner"
    assert listed["department"] == "AI Platform"
    assert listed["daily_budget"] == 45.0
    assert listed["execution_count"] == 1

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["name"] == "Planner"
    assert detail["provider"] == "openai"
    assert detail["model"] == "gpt-4o"
    assert detail["permissions"] == ["plan:create", "context:read"]
    assert detail["connected_tools"] == ["rag_search", "tool_router"]

    assert history_response.status_code == 200
    assert history_response.json()["history"][0]["action_summary"] == "Built an incident response plan"

    assert policies_response.status_code == 200
    assert policies_response.json()["policies"][0]["name"] == "planner-default-allow"

    assert tools_response.status_code == 200
    assert tools_response.json()["tools"] == ["rag_search", "tool_router"]
    assert tools_response.json()["permissions"] == ["plan:create", "context:read"]

    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert metrics["execution_count"] == 1
    assert metrics["history_count"] == 1
    assert metrics["success_rate"] == 100.0
    assert missing_response.status_code == 404


def test_governance_audit_verify_and_csv_export_routes(tmp_path: Path) -> None:
    app, auth_manager = _build_governance_app(tmp_path)
    user = auth_manager.user_store.create_user("audit@example.com", "password12345", role="auditor")
    app.state.governance.register_agent(_agent("audited-agent", "Audited Agent"))
    app.state.governance.record_action(
        AgentAction(
            action_id="audit-route-1",
            agent_id="audited-agent",
            action_type="query",
            action_summary="Collected evidence",
            target_resource="/api/audit",
            policy_verdict="allowed",
            status="success",
        )
    )

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        token = auth_manager.create_access_token(user)
        cookies = {"aegisnex_session": token}
        verify_response = client.get("/api/governance/audit/verify", cookies=cookies)
        export_response = client.get("/api/governance/audit/export.csv", cookies=cookies)

    assert verify_response.status_code == 200
    assert verify_response.json()["valid"] is True
    assert verify_response.json()["total_entries"] == 1
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    assert "audit-route-1" in export_response.text
    assert "entry_hash" in export_response.text
