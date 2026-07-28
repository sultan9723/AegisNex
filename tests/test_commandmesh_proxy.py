import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.ai_governance import AIAgent, AgentPolicy, GovernanceManager
from src.auth import AuthManager, UserStore, generate_api_key
from src.dashboard import create_app
from src.intelligence.providers.base import Message, ModelProvider, ProviderConfig
from src.platform_db import PlatformRepository

from tests.test_dashboard import build_services


class FakeCommandMeshProvider(ModelProvider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or ProviderConfig(model="fake-fast"))
        self.last_messages: list[Message] = []

    def chat(self, messages: list[Message], **kwargs: Any) -> Message:
        self.last_messages = messages
        return Message(role="assistant", content="proxy response")

    def chat_with_tools(self, messages: list[Message], tools: list[dict[str, Any]], **kwargs: Any) -> Message:
        self.last_messages = messages
        return Message(role="assistant", content="tool proxy response")

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        return [0.1, 0.2, 0.3]

    @property
    def provider_name(self) -> str:
        return "fake"


def _build_proxy_app(tmp_path: Path):
    services = build_services(tmp_path)
    services.platform_repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    services.monitoring_engine = None
    auth_manager = AuthManager(
        UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    app = create_app(services, auth_manager=auth_manager)
    app.state.governance = GovernanceManager(tmp_path / "governance.db")
    app.state.commandmesh_provider_factory = lambda provider_name="fake": FakeCommandMeshProvider()
    full_key, key_hash, key_prefix = generate_api_key()
    services.platform_repository.create_api_key("proxy-test", key_hash, key_prefix, role="administrator")
    return app, full_key


def _register_proxy_agent(gov: GovernanceManager) -> None:
    gov.register_agent(
        AIAgent(
            agent_id="test-proxy-agent",
            name="Test Proxy Agent",
            agent_type="proxy",
            description="Proxy route test agent",
            owner="platform",
            team="qa",
        )
    )


def _policy(name: str, effect: str, priority: int = 10) -> AgentPolicy:
    return AgentPolicy(
        policy_id=0,
        name=name,
        description=f"{effect} chat completions",
        policy_type="routing",
        target_agents='["test-proxy-agent"]',
        conditions='{"action_type": "chat_completion"}',
        effect=effect,
        priority=priority,
    )


def test_openai_proxy_allows_chat_completion_and_records_action(tmp_path: Path) -> None:
    app, api_key = _build_proxy_app(tmp_path)
    _register_proxy_agent(app.state.governance)
    app.state.governance.create_policy(_policy("allow-chat", "allow"))

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": "test-proxy-agent"},
            json={
                "model": "fake-fast",
                "messages": [{"role": "user", "content": "Summarize spend"}],
            },
        )
        summary_response = client.get(
            "/api/governance/costs/summary",
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert summary_response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "gpt-4o-mini"
    assert body["choices"][0]["message"]["content"] == "proxy response"
    assert body["commandmesh"]["policy_verdict"] == "allowed"
    assert body["commandmesh"]["routing"]["requested_model"] == "fake-fast"
    assert body["commandmesh"]["routing"]["selected_tier"] == "cheap"
    assert body["commandmesh"]["cost"]["estimated_selected_usd"] >= 0
    actions = app.state.governance.list_actions(agent_id="test-proxy-agent")
    assert len(actions) == 1
    assert actions[0].status == "success"
    assert actions[0].action_type == "chat_completion"
    assert json.loads(actions[0].outputs)["routing"]["selected_model"] == "gpt-4o-mini"
    summary = summary_response.json()
    assert summary["total_calls"] == 1
    assert summary["by_model"]["gpt-4o-mini"]["calls"] == 1
    assert summary["by_tier"]["cheap"]["calls"] == 1


def test_openai_proxy_denies_policy_blocked_call(tmp_path: Path) -> None:
    app, api_key = _build_proxy_app(tmp_path)
    _register_proxy_agent(app.state.governance)
    app.state.governance.create_policy(_policy("deny-chat", "deny"))

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": "test-proxy-agent"},
            json={
                "model": "fake-fast",
                "messages": [{"role": "user", "content": "Do risky thing"}],
            },
        )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["type"] == "denied"
    actions = app.state.governance.list_actions(agent_id="test-proxy-agent")
    assert len(actions) == 1
    assert actions[0].status == "blocked"
    assert actions[0].policy_verdict == "denied"


def test_openai_proxy_creates_approval_for_pending_policy(tmp_path: Path) -> None:
    app, api_key = _build_proxy_app(tmp_path)
    _register_proxy_agent(app.state.governance)
    app.state.governance.create_policy(_policy("approve-chat", "approve"))

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": "test-proxy-agent"},
            json={
                "model": "fake-frontier",
                "messages": [{"role": "user", "content": "Review production deploy"}],
            },
        )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["type"] == "pending_approval"
    assert body["error"]["approval_id"]
    approvals = app.state.services.platform_repository.list_approval_requests(status="pending")
    assert len(approvals) == 1
    assert approvals[0]["approval_id"] == body["error"]["approval_id"]


def test_openai_proxy_rejects_streaming_for_v1(tmp_path: Path) -> None:
    app, api_key = _build_proxy_app(tmp_path)

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "fake-fast",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "unsupported_feature"


def test_openai_proxy_respects_locked_model_metadata(tmp_path: Path) -> None:
    app, api_key = _build_proxy_app(tmp_path)
    _register_proxy_agent(app.state.governance)
    app.state.governance.create_policy(_policy("allow-locked-chat", "allow"))

    with TestClient(app) as client:
        app.state.governance = GovernanceManager(tmp_path / "governance.db")
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": "test-proxy-agent"},
            json={
                "model": "fake-frontier",
                "metadata": {"model_locked": True},
                "messages": [{"role": "user", "content": "Summarize spend"}],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "fake-frontier"
    assert body["commandmesh"]["routing"]["selected_tier"] == "locked"
    assert body["commandmesh"]["routing"]["routing_disabled"] is True
