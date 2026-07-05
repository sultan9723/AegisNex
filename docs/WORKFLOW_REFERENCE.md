# Workflow Reference

## LangGraph Workflow Diagram

```
                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
              ┌─────│   Planner   │─────┐
              │     └─────────────┘     │
              │                        │
        ┌─────┴─────┐          ┌───────┴────────┐
        │ Skills    │          │  Tool Executor  │
        │ Matched   │          │  Plan Exists    │
        └─────┬─────┘          └───────┬────────┘
              │                        │
        ┌─────▼──────┐          ┌──────▼────────┐
        │Skill Exec. │          │ Tool Executor │
        └─────┬──────┘          └──────┬────────┘
              │                        │
              │          ┌─────────────┼─────────────┐
              │          │ Pending     │              │
              │          │ Approval    │ No Approval  │
              │          └──────┬──────┘              │
              │                 │                     │
              │         ┌───────▼────────┐    ┌───────▼────────┐
              │         │ Goal Evaluator │    │   Verifier     │
              │         └───────────────┘    └───────┬────────┘
              │                                     │
              │                          ┌──────────┼──────────┐
              │                          │ Errors   │ OK       │
              │                          └────┬─────┘          │
              │                               │                │
              │                        ┌──────▼──────┐         │
              │                        │Self-Correct │         │
              │                        └──────┬──────┘         │
              │                               │                │
              │                     ┌─────────┼──────────┐     │
              │                     │Re-plan  │ End      │     │
              │                     └───┬─────┘          │     │
              │                         │                │     │
              │                         ▼                ▼     │
              │                    ┌─────────┐     ┌───────────┘
              │                    │ Planner │     │
              │                    └─────────┘     │
              │                    ┌───────────────▼──────┐
              │                    │   Goal Evaluator     │
              │                    └──────────┬───────────┘
              │                               │
              │                    ┌──────────▼───────────┐
              │                    │      Learning        │
              │                    └──────────┬───────────┘
              │                               │
              │                               ▼
              │                    ┌──────────────────┐
              │                    │       END        │
              │                    └──────────────────┘
              │
              │ (Alternative paths from Planner)
              │
              ├── Runbook Trigger ──▶ Runbook Executor ──▶ Scheduler ──▶ Policy Check ──▶ Risk Assess ──▶ Verifier
              │
              └── Parallel Batches ──▶ Parallel Supervisor ──▶ Scheduler ──▶ Policy Check ──▶ Risk Assess ──▶ Verifier
```

---

## Node Descriptions

### 1. `planner`
Analyzes the user request, retrieves context via RAG, and builds a structured plan. Detects intent using keyword matching against incident, metric, Docker, health, audit, report, and notification keywords. Produces `objective`, `current_plan` (ordered tool list), `parallel_batches`, and `missing_info`.

### 2. `skill_executor`
Auto-selects AI skills via keyword matching against skill names, descriptions, and required tools. Executes matched skills using the `SkillEngine` and stores results in `skill_results`. Supported skills: SystemAnalyzer, IncidentInvestigator, ContainerManager, ReportGenerator, SecurityAuditor.

### 3. `tool_executor`
Iterates through the plan's tool list, optionally in parallel batches. Checks each tool for `requires_approval` — if flagged, creates a `PendingApproval` and skips execution. Otherwise executes via `execute_tool()`. Stores results per tool in `tool_results`.

### 4. `verifier`
Calculates confidence as `successful_tools / total_tools`. Produces observations, evidence strings, `reasoning_summary`, and `remaining_uncertainty`. Routes to `self_corrector` if errors exist or `goal_evaluator` if successful.

### 5. `self_corrector`
Handles tool failures with retries (max 3). Applies correction strategies: substitutes Docker with metrics+health, retries monitoring checks, falls back on DB errors, skips failed services. Determines whether to re-plan (return to planner) or end.

### 6. `goal_evaluator`
Produces the `final_answer` markdown with results, evidence, observations, corrections, errors, and status. Sets `goal_achieved` based on data presence, critical errors, confidence threshold (>0.6 or >0.3 with data), and retry exhaustion.

### 7. `risk_assessor`
Uses `RiskEngine` to score the current tool on a 0–1 scale. If score >= 0.5, sets `approval_required` and creates a `PendingApproval`. Stores `risk_assessment` dict in state.

### 8. `policy_checker`
Evaluates the planned action against 6 default policies using `PolicyEngine`. Stores `policy_results` and may create `PendingApproval` if a policy requires it.

### 9. `runbook_executor`
Selects and executes a runbook. Runbook name comes from the planner or is matched via workflow library trigger keywords. Steps with `requires_approval` create pending approvals. Results stored in `runbook_steps` and merged into `tool_results`.

### 10. `parallel_supervisor`
Fans out parallel batches of tools, executing each batch and merging results. Used when the planner identifies independent work streams.

### 11. `scheduler`
Queries the `Scheduler` for pending scheduled tasks. Returns task list in `scheduler_tasks`.

### 12. `learning`
Persists learnings to the memory store on each execution cycle. Records error patterns (root cause + resolution) and success patterns. Learnings are stored in `ai_learnings` table.

---

## Edge Conditions

| From                  | To                  | Condition                                          |
|-----------------------|---------------------|----------------------------------------------------|
| `planner`             | `skill_executor`    | `state.active_skills` non-empty                    |
| `planner`             | `runbook_executor`  | `state.current_runbook` or `workflow_triggered`    |
| `planner`             | `parallel_supervisor`| `state.parallel_batches` non-empty                |
| `planner`             | `tool_executor`     | `state.current_plan` exists                        |
| `planner`             | `goal_evaluator`    | No plan                                            |
| `tool_executor`       | `verifier`          | No pending approvals                               |
| `tool_executor`       | `goal_evaluator`    | Pending approval exists                            |
| `runbook_executor`    | `scheduler`         | Always                                             |
| `parallel_supervisor` | `scheduler`         | Always                                             |
| `scheduler`           | `policy_checker`    | Always                                             |
| `policy_checker`      | `risk_assessor`     | Always                                             |
| `risk_assessor`       | `verifier`          | Auto-approved (risk < threshold)                   |
| `risk_assessor`       | `goal_evaluator`    | Approval required                                  |
| `verifier`            | `goal_evaluator`    | `should_continue` returns "end"                    |
| `verifier`            | `self_corrector`    | `should_continue` returns "correct"                |
| `self_corrector`      | `goal_evaluator`    | `should_continue` returns "end"                    |
| `self_corrector`      | `planner`           | `should_continue` returns "correct"                |

---

## Workflow Designer

The workflow designer (`src/workflow_designer/`) allows visual creation of custom workflows.

### Node Types

| Type              | Description                                    | Config Fields                    |
|-------------------|------------------------------------------------|----------------------------------|
| `TRIGGER`         | Entry point — starts the workflow              | `trigger_keywords`, `schedule`   |
| `AI_PLANNING`     | Uses the LangGraph planner to create a plan    | `provider`, `model`              |
| `TOOL_EXECUTION`  | Executes a specific tool                       | `tool_name`, `params`            |
| `APPROVAL`        | Human approval gate                            | `message`, `timeout_minutes`     |
| `RUNBOOK`         | Executes a runbook by name                     | `runbook_name`, `params`         |
| `NOTIFICATION`    | Sends a notification                           | `channel`, `template`            |
| `CONDITION`       | Branching logic (≥2 outputs)                   | `expression`                     |
| `END`             | Terminal node                                  | `summary_template`               |

### Creating Custom Workflows

Workflows are created via the visual designer (UI) and serialized as JSON. The `WorkflowDefinition` model supports nodes, edges, validation, and execution graph generation.

```json
{
  "id": "custom-remediation",
  "name": "Custom Remediation",
  "nodes": [
    { "id": "trigger-1", "type": "TRIGGER", "label": "Alert Trigger",
      "config": { "trigger_keywords": ["high cpu", "memory leak"] } },
    { "id": "tool-1", "type": "TOOL_EXECUTION", "label": "Get Metrics",
      "config": { "tool_name": "metrics" } },
    { "id": "approval-1", "type": "APPROVAL", "label": "Approve Restart",
      "config": { "message": "Restart container?" } },
    { "id": "end-1", "type": "END", "label": "Done" }
  ],
  "edges": [
    { "id": "e1", "source": "trigger-1", "target": "tool-1" },
    { "id": "e2", "source": "tool-1", "target": "approval-1" },
    { "id": "e3", "source": "approval-1", "target": "end-1" }
  ]
}
```

---

## Example Workflows

### Incident Response Workflow

Trigger: `incident_pattern` → `["incident", "alert", "down", "unreachable"]`

| Step     | Action                        | Tool       | Parallel |
|----------|-------------------------------|------------|----------|
| 1        | Check HTTP/SSL/TCP targets    | `target`   | Yes      |
| 2        | Check Docker containers       | `docker`   | Yes      |
| 3        | List active incidents         | `incident` | No       |
| 4        | Analyze audit logs            | `audit`    | No       |
| 5        | Generate summary report       | `report`   | No       |
| 6        | Notify operator               | —          | No       |

### Scheduled Health Check Workflow

Trigger: `cron(0 */5 * * *)`

| Step     | Action                        | Tool       | Parallel |
|----------|-------------------------------|------------|----------|
| 1        | Collect system metrics        | `metrics`  | No       |
| 2        | Check all containers          | `docker`   | Yes      |
| 3        | Check HTTP targets            | `target`   | Yes      |
| 4        | Save metrics snapshot         | —          | No       |
| 5        | Evaluate against alert rules  | —          | No       |
| 6        | Send notification if critical | —          | No       |

### Deployment Pipeline Workflow

Trigger: `deployment_pattern` → `["deploy", "update", "rollout"]`

| Step     | Action                        | Tool       | Requires Approval |
|----------|-------------------------------|------------|--------------------|
| 1        | Pre-deployment health check   | `health`   | No                |
| 2        | Verify current state          | `docker`   | No                |
| 3        | Run deployment script         | —          | Yes (operator)    |
| 4        | Verify post-deployment health | `health`   | No                |
| 5        | Notify team                   | `notification`| No              |

---

## Runbook YAML Format

```yaml
name: high-cpu
description: Investigate and resolve high CPU usage
version: "1.0"
category: performance
tags:
  - cpu
  - performance
  - metrics
timeout_seconds: 180
requires_incident: true
parallel_steps:
  - ["step-1", "step-2"]
steps:
  - name: collect-metrics
    action: tool
    tool: metrics
    description: Collect current system metrics
    on_failure: stop
  - name: identify-top-consumers
    action: tool
    tool: docker
    description: Identify top resource-consuming containers
    on_failure: continue
  - name: restart-heavy-container
    action: tool
    tool: docker
    params:
      action: restart
    description: Restart the heaviest container
    requires_approval: true
    on_failure: continue
  - name: close-incident
    action: resolve_incident
    params:
      resolution_notes: "High CPU resolved by restarting top consumer"
    description: Close incident
```

### Runbook Step Actions

| Action             | Description                                |
|--------------------|--------------------------------------------|
| `tool`             | Execute a registered tool                   |
| `wait`             | Sleep for specified seconds                |
| `notify`           | Send a notification                        |
| `resolve_incident` | Resolve an incident by ID                  |
| `create_incident`  | Create a new incident                      |
