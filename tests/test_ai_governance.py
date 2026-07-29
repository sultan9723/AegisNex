import json
import sqlite3
from pathlib import Path

from src.ai_governance import (
    AIAgent,
    ActionVerdict,
    AgentAction,
    AgentAnomaly,
    AgentPolicy,
    GovernanceManager,
    PolicyEffect,
    RiskLevel,
)


def _agent(agent_id: str, *, max_actions_per_hour: int = 100) -> AIAgent:
    return AIAgent(
        agent_id=agent_id,
        name=f"Agent {agent_id}",
        agent_type="test",
        description="Test agent",
        owner="platform",
        team="qa",
        allowed_tools=json.dumps(["query"]),
        allowed_resources=json.dumps(["/api/test"]),
        max_actions_per_hour=max_actions_per_hour,
    )


def test_governance_registry_is_tenant_scoped(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "governance.db")

    gov.register_agent(_agent("agent-1"), tenant_id="org:1")
    gov.register_agent(_agent("agent-1"), tenant_id="org:2")

    assert gov.get_agent("agent-1", tenant_id="org:1") is not None
    assert gov.get_agent("agent-1", tenant_id="org:2") is not None
    assert gov.get_agent("agent-1", tenant_id="org:3") is None

    org1_agents = gov.list_agents(tenant_id="org:1")
    org2_agents = gov.list_agents(tenant_id="org:2")
    assert [a.agent_id for a in org1_agents] == ["agent-1"]
    assert [a.agent_id for a in org2_agents] == ["agent-1"]
    assert org1_agents[0].tenant_id == "org:1"
    assert org2_agents[0].tenant_id == "org:2"


def test_governance_migrates_legacy_global_unique_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_governance.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE ai_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                agent_type TEXT NOT NULL DEFAULT 'general',
                description TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT 'system',
                team TEXT NOT NULL DEFAULT 'platform',
                status TEXT NOT NULL DEFAULT 'active',
                risk_level TEXT NOT NULL DEFAULT 'medium',
                trust_score REAL NOT NULL DEFAULT 50.0,
                allowed_tools TEXT NOT NULL DEFAULT '[]',
                allowed_resources TEXT NOT NULL DEFAULT '[]',
                max_actions_per_hour INTEGER NOT NULL DEFAULT 100,
                total_actions INTEGER NOT NULL DEFAULT 0,
                total_denied INTEGER NOT NULL DEFAULT 0,
                total_anomalies INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_active_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ai_agents (
                agent_id, name, agent_type, description, owner, team, status, risk_level,
                trust_score, allowed_tools, allowed_resources, max_actions_per_hour,
                total_actions, total_denied, total_anomalies, created_at, updated_at, last_active_at
            ) VALUES (
                'agent-1', 'Legacy Agent', 'test', 'legacy', 'platform', 'qa', 'active', 'medium',
                50.0, '[]', '[]', 100, 0, 0, 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', NULL
            )
            """
        )

    gov = GovernanceManager(db_path)
    gov.register_agent(_agent("agent-1"), tenant_id="org:2")

    assert gov.get_agent("agent-1", tenant_id="default") is not None
    assert gov.get_agent("agent-1", tenant_id="org:2") is not None


def test_governance_policy_evaluation_is_tenant_scoped(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "governance.db")
    gov.register_agent(_agent("writer"), tenant_id="org:1")
    gov.register_agent(_agent("writer"), tenant_id="org:2")

    gov.create_policy(
        AgentPolicy(
            policy_id=0,
            name="deny-prod-write",
            description="Deny production writes",
            policy_type="access_control",
            target_agents=json.dumps(["writer"]),
            conditions=json.dumps({"action_type": "write", "target_pattern": "prod"}),
            effect=PolicyEffect.DENY.value,
            priority=1,
        ),
        tenant_id="org:1",
    )

    org1_verdict, org1_reason = gov.evaluate_policies("writer", "write", "/prod/db", tenant_id="org:1")
    org2_verdict, org2_reason = gov.evaluate_policies("writer", "write", "/prod/db", tenant_id="org:2")

    assert org1_verdict == ActionVerdict.DENIED.value
    assert org1_reason == "Denied by policy: deny-prod-write"
    assert org2_verdict == ActionVerdict.ALLOWED.value
    assert org2_reason is None


def test_governance_actions_and_stats_are_tenant_scoped(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "governance.db")
    gov.register_agent(_agent("audited"), tenant_id="org:1")
    gov.register_agent(_agent("audited"), tenant_id="org:2")

    gov.record_action(
        AgentAction(
            action_id="act-1",
            agent_id="audited",
            action_type="write",
            action_summary="Denied write",
            target_resource="/prod",
            policy_verdict=ActionVerdict.DENIED.value,
        ),
        tenant_id="org:1",
    )
    gov.record_action(
        AgentAction(
            action_id="act-1",
            agent_id="audited",
            action_type="query",
            action_summary="Allowed query",
            target_resource="/status",
            policy_verdict=ActionVerdict.ALLOWED.value,
        ),
        tenant_id="org:2",
    )

    assert gov.get_agent("audited", tenant_id="org:1").total_denied == 1
    assert gov.get_agent("audited", tenant_id="org:2").total_denied == 0
    assert gov.get_action("act-1", tenant_id="org:1").action_type == "write"
    assert gov.get_action("act-1", tenant_id="org:2").action_type == "query"

    org1_stats = gov.get_agent_stats(tenant_id="org:1")
    org2_stats = gov.get_agent_stats(tenant_id="org:2")
    assert org1_stats["total_actions"] == 1
    assert org1_stats["total_denied"] == 1
    assert org2_stats["total_actions"] == 1
    assert org2_stats["total_denied"] == 0


def test_action_audit_chain_is_hash_chained_and_exportable(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "governance.db")
    gov.register_agent(_agent("audited"))

    first = gov.record_action(
        AgentAction(
            action_id="audit-1",
            agent_id="audited",
            action_type="query",
            action_summary="First action",
            target_resource="/status",
        )
    )
    second = gov.record_action(
        AgentAction(
            action_id="audit-2",
            agent_id="audited",
            action_type="write",
            action_summary="Second action",
            target_resource="/prod",
            policy_verdict=ActionVerdict.DENIED.value,
            status="denied",
        )
    )

    assert first.previous_hash == ""
    assert first.entry_hash
    assert second.previous_hash == first.entry_hash
    assert second.entry_hash

    verification = gov.verify_action_audit_chain()
    assert verification["valid"] is True
    assert verification["total_entries"] == 2
    assert verification["head_hash"] == second.entry_hash

    csv_export = gov.export_action_audit_csv()
    assert "tenant_id,action_id,agent_id" in csv_export
    assert "audit-1" in csv_export
    assert first.entry_hash in csv_export


def test_action_audit_chain_detects_tampering(tmp_path: Path) -> None:
    db_path = tmp_path / "governance.db"
    gov = GovernanceManager(db_path)
    gov.register_agent(_agent("audited"))
    gov.record_action(
        AgentAction(
            action_id="audit-1",
            agent_id="audited",
            action_type="query",
            action_summary="Original summary",
            target_resource="/status",
        )
    )

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE agent_actions SET action_summary = ? WHERE action_id = ?",
            ("Tampered summary", "audit-1"),
        )

    verification = gov.verify_action_audit_chain()
    assert verification["valid"] is False
    assert verification["first_invalid_action_id"] == "audit-1"
    assert verification["errors"][0]["error"] == "entry_hash_mismatch"


def test_governance_anomalies_are_tenant_scoped(tmp_path: Path) -> None:
    gov = GovernanceManager(tmp_path / "governance.db")
    gov.register_agent(_agent("burst", max_actions_per_hour=1), tenant_id="org:1")
    gov.register_agent(_agent("burst", max_actions_per_hour=100), tenant_id="org:2")

    for i in range(2):
        gov.record_action(
            AgentAction(
                action_id=f"org1-act-{i}",
                agent_id="burst",
                action_type="query",
                action_summary="Burst action",
                target_resource="/api/test",
            ),
            tenant_id="org:1",
        )
    gov.record_action(
        AgentAction(
            action_id="org2-act-1",
            agent_id="burst",
            action_type="query",
            action_summary="Normal action",
            target_resource="/api/test",
        ),
        tenant_id="org:2",
    )

    detected_org1 = gov.detect_anomalies(tenant_id="org:1")
    detected_org2 = gov.detect_anomalies(tenant_id="org:2")

    assert [a["anomaly_type"] for a in detected_org1] == ["action_burst"]
    assert detected_org2 == []
    assert len(gov.list_anomalies(tenant_id="org:1")) == 1
    assert len(gov.list_anomalies(tenant_id="org:2")) == 0

    anomaly = gov.record_anomaly(
        AgentAnomaly(
            anomaly_id=0,
            agent_id="burst",
            anomaly_type="manual_review",
            description="Manual review required",
            severity=RiskLevel.MEDIUM.value,
        ),
        tenant_id="org:2",
    )
    assert gov.resolve_anomaly(anomaly.anomaly_id, "reviewer@example.com", tenant_id="org:1") is False
    assert gov.resolve_anomaly(anomaly.anomaly_id, "reviewer@example.com", tenant_id="org:2") is True
