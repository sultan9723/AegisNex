# Agent Reference

## Multi-Agent System Overview

The AegisNex Multi-Agent Collaboration module (`src/agents/`) provides a framework of specialized supervisor agents managed by an `AgentOrchestrator`. Each agent has a defined role, allowed tools, and collaboration capabilities.

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              SharedAgentState                       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  dispatch_task(task, target_agent)        fan_out(task)     │
│  collaborate(agent_ids, task)            get_shared_state() │
│  list_agents()                            register_agent()  │
└────────┬──────────┬──────────┬──────────┬───────────────────┘
         │          │          │          │
    ┌────▼────┐ ┌───▼────┐ ┌──▼────┐ ┌───▼────────┐
    │Operations│ │Security│ │Compl. │ │Infrastructure│
    │Supervisor│ │Superv. │ │Superv.│ │Supervisor   │
    └─────────┘ └────────┘ └───────┘ └─────────────┘
```

---

## Agent Types

### AgentType Enum

| Value            | Description                          |
|------------------|--------------------------------------|
| `operations`     | System ops, monitoring, Docker       |
| `security`       | Security scanning, audit, threats    |
| `compliance`     | Compliance checks, evidence, reports |
| `infrastructure` | Infra management, scaling, K8s       |
| `general`        | Fallback/catch-all agent             |

---

## Agent Details

### OperationsSupervisor

| Property        | Value                                    |
|-----------------|------------------------------------------|
| **ID**          | `ops-supervisor-001`                     |
| **Name**        | Operations Supervisor                    |
| **Description** | System operations, monitoring, Docker containers, incident response |
| **Allowed Tools** | `metrics`, `docker`, `incident`, `notification`, `health` |

**Prompt:** "You are the Operations Supervisor. Your role is to monitor system health, manage Docker containers, investigate incidents, and maintain operational stability."

**Collaboration Messages:**
| Message Type          | Responds With        | Payload                              |
|-----------------------|----------------------|--------------------------------------|
| `request_metrics`     | `metrics_data`       | `{metrics, health}`                  |
| `request_incidents`   | `incident_data`      | `{incidents}`                        |

### SecuritySupervisor

| Property        | Value                                    |
|-----------------|------------------------------------------|
| **ID**          | `sec-supervisor-001`                     |
| **Name**        | Security Supervisor                      |
| **Description** | Security scanning, audit log review, threat detection |
| **Allowed Tools** | `audit`, `incident`, `notification`    |

**Prompt:** "You are the Security Supervisor. Your role is to review audit logs, detect security threats, monitor incidents for security patterns, and ensure the platform remains secure."

**Collaboration Messages:**
| Message Type          | Responds With        | Payload                              |
|-----------------------|----------------------|--------------------------------------|
| `request_audit`       | `audit_data`         | `{audit_logs}`                       |
| `security_check`      | `security_findings`  | `{findings}`                         |

### ComplianceSupervisor

| Property        | Value                                    |
|-----------------|------------------------------------------|
| **ID**          | `comp-supervisor-001`                    |
| **Name**        | Compliance Supervisor                    |
| **Description** | Compliance checks, evidence collection, audit reporting |
| **Allowed Tools** | `audit`, `report`, `notification`, `health` |

**Prompt:** "You are the Compliance Supervisor. Your role is to perform compliance checks, collect evidence from audit logs and system state, generate compliance reports, and ensure adherence to organizational policies."

**Collaboration Messages:**
| Message Type              | Responds With        | Payload                              |
|---------------------------|----------------------|--------------------------------------|
| `request_compliance_report` | `compliance_report`  | `{report}`                           |
| `request_evidence`        | `evidence_data`      | `{evidence, audit_logs}`             |

### InfrastructureSupervisor

| Property        | Value                                    |
|-----------------|------------------------------------------|
| **ID**          | `infra-supervisor-001`                   |
| **Name**        | Infrastructure Supervisor                |
| **Description** | Infrastructure management, Docker orchestration, scaling decisions |
| **Allowed Tools** | `docker`, `metrics`, `health`, `notification`, `incident` |

**Prompt:** "You are the Infrastructure Supervisor. Your role is to manage infrastructure resources, monitor Docker containers, assess scaling needs, and ensure infrastructure reliability."

**Collaboration Messages:**
| Message Type                    | Responds With         | Payload                              |
|---------------------------------|-----------------------|--------------------------------------|
| `request_infrastructure_status` | `infrastructure_status`| `{docker, health}`                   |
| `request_scaling_analysis`      | `scaling_analysis`    | `{metrics, containers}`              |

---

## Orchestrator

The `AgentOrchestrator` (`src/agents/orchestrator.py`) manages the full agent lifecycle.

### Dispatch

Sends a task to a specific agent or auto-selects the best agent based on keyword matching:

```python
await orchestrator.dispatch_task(task="investigate high CPU", target_agent="ops-supervisor-001")
```

Auto-selection logic:
- `operations` — keywords: incident, alert, docker, container, cpu, memory, metric
- `security` — keywords: security, audit, threat, log, vulnerability, breach
- `compliance` — keywords: compliance, report, policy, evidence, regulation
- `infrastructure` — keywords: infrastructure, scale, kubernetes, k8s, capacity, resource

### Fan-Out

Broadcasts the same task to all enabled agents in parallel:

```python
await orchestrator.fan_out(task="system health check")
```

Returns `List[AgentResult]` with per-agent success, summary, data, and duration.

### Collaboration

Engages specific agents in a message exchange for a shared task. The orchestrator broadcasts a `collaboration_request` message and collects all agent responses:

```python
await orchestrator.collaborate(agent_ids=["ops-supervisor-001", "sec-supervisor-001"], task="security incident investigation")
```

---

## Shared State Model

`SharedAgentState` (`src/agents/state.py`) provides thread-safe key-value storage for inter-agent data sharing.

| Method                   | Description                              |
|--------------------------|------------------------------------------|
| `set(key, value, agent_id)` | Store value with optional agent attribution |
| `get(key)`               | Retrieve value by key                    |
| `get_all()`              | Retrieve entire state dict               |
| `get_history(limit)`     | Get state change history                 |
| `clear()`                | Reset all state                          |

State changes are logged with agent_id and timestamp for auditability.

---

## Adding Custom Agents

### 1. Define the Agent Class

```python
from src.agents.base import BaseAgent, AgentConfig, AgentType, AgentMessage, AgentResult
from src.intelligence.graph import run_workflow

class DatabaseSupervisor(BaseAgent):
    def __init__(self):
        config = AgentConfig(
            agent_id="db-supervisor-001",
            name="Database Supervisor",
            agent_type=AgentType.GENERAL,
            description="Database performance monitoring and optimization",
            allowed_tools=["metrics", "health", "incident"],
            supervisor_prompt="You are the Database Supervisor...",
        )
        super().__init__(config)

    async def process(self, task: str, shared_state: dict) -> AgentResult:
        result = run_workflow(task)
        return AgentResult(
            agent_id=self.agent_id,
            success=result.get("goal_achieved", False),
            summary=result.get("final_answer", "")[:200],
            data=result,
            duration_ms=0.0,
        )

    async def collaborate(self, messages: list[AgentMessage]) -> list[AgentMessage]:
        # Handle inter-agent messages
        return []
```

### 2. Register with the Orchestrator

```python
orchestrator = AgentOrchestrator()
orchestrator.register_agent(DatabaseSupervisor())
```

### 3. (Optional) Add Auto-Selection Keywords

Update `_select_best_agent` in `AgentOrchestrator` to include keywords for the new agent.

### 4. Expose via API

Agents registered in `create_app()` lifespan are automatically available via `/api/agents/*` endpoints.
