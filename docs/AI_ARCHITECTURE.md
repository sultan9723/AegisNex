# AI Architecture

## LangGraph Workflow

The Intelligence Engine is built on `langgraph` with a `StateGraph` that routes through up to 12 nodes with conditional edges for self-correction, approval gates, and parallel execution.

### Diagram

```
  START
    │
    ▼
┌──────────┐
│ Planner  │────────────────────────────────────────────────────────┐
└────┬─────┘                                                        │
     │                                                              │
     ├──[active_skills]──────▶ skill_executor ──▶ tool_executor     │
     ├──[runbook/trigger]────▶ runbook_executor ──▶ scheduler       │
     ├──[parallel_batches]──▶ parallel_supervisor ──▶ scheduler     │
     ├──[plan exists]───────▶ tool_executor                         │
     └──[empty plan]───────▶ goal_evaluator                         │
                                                                    │
                              tool_executor                         │
                                │                                   │
                          ┌─────┴──────┐                            │
                    [pending_approval] │                            │
                          ▼            ▼                            │
                   goal_evaluator   verifier                        │
                                      │                             │
                                  ┌───┴───┐                         │
                             [errors]  [ok]                         │
                                  ▼       ▼                         │
                           self_corrector goal_evaluator            │
                                  │              │                  │
                              ┌───┴───┐          │                  │
                         [replan] [end]          │                              │
                              ▼       ▼          │
                          planner  goal_evaluator│
                                       │         │
                                       ▼         │
                                   learning      │
                                       │         │
                                       ▼         │
                                      END ◀──────┘
```

### Node Descriptions

| # | Node               | Function                                                                 |
|---|--------------------|-------------------------------------------------------------------------|
| 1 | `planner`          | Analyzes user request, retrieves RAG context, builds plan + parallel batches |
| 2 | `skill_executor`   | Auto-selects and executes AI skills matched to the request               |
| 3 | `tool_executor`    | Executes each tool in the plan serially/by batch; checks for approvals   |
| 4 | `verifier`         | Verifies tool results, calculates confidence score, populates evidence   |
| 5 | `self_corrector`   | Handles failures — retries tools or adjusts plan up to max_retries (3)  |
| 6 | `goal_evaluator`   | Produces final_answer, determines goal_achieved, suggests manual invest. |
| 7 | `risk_assessor`    | Scores each tool action for risk (0–1); triggers approval if ≥ 0.5       |
| 8 | `policy_checker`   | Evaluates 6 default policies before allowing actions                     |
| 9 | `runbook_executor` | Parses and executes runbooks via RunbookEditor                          |
| 10| `parallel_supervisor`| Fans out parallel batches and merges results                            |
| 11| `scheduler`        | Checks and returns pending scheduled tasks from the scheduler DB         |
| 12| `learning`         | Stores learnings from errors, corrections, and success patterns          |

### Edge Conditions

| From              | To               | Condition                                  |
|-------------------|------------------|--------------------------------------------|
| `planner`         | `skill_executor` | `state.active_skills` is non-empty         |
| `planner`         | `runbook_executor`| `state.current_runbook` or workflow triggered |
| `planner`         | `parallel_supervisor`| `state.parallel_batches` is non-empty    |
| `planner`         | `tool_executor`  | `state.current_plan` exists                |
| `planner`         | `goal_evaluator` | No plan generated                          |
| `tool_executor`   | `verifier`       | No pending approvals                       |
| `tool_executor`   | `goal_evaluator` | Pending approval                           |
| `risk_assessor`   | `verifier`       | Auto-approved (risk < threshold)           |
| `risk_assessor`   | `goal_evaluator` | Requires approval                          |
| `verifier`        | `goal_evaluator` | Goal achieved or max retries reached       |
| `verifier`        | `self_corrector` | Errors detected                            |
| `self_corrector`  | `goal_evaluator` | Goal achieved or max retries reached       |
| `self_corrector`  | `planner`        | Re-plan needed                             |

---

## AgentState — All Fields

The `AgentState` (`src/intelligence/state.py`) is a `TypedDict` with these fields:

| Field                     | Type                  | Purpose                                      |
|---------------------------|-----------------------|----------------------------------------------|
| `user_request`            | `str`                 | Original user input                          |
| `objective`               | `str`                 | Planner-determined objective                 |
| `current_plan`            | `List[str]`           | Ordered list of tool steps                   |
| `completed_steps`         | `List[str]`           | Steps already executed                       |
| `tool_results`            | `Dict[str, Any]`      | Results keyed by tool name                   |
| `observations`            | `List[str]`           | Human-readable observations                  |
| `confidence`              | `float`               | Verifier confidence (0–1)                    |
| `retries`                 | `int`                 | Current retry count                          |
| `max_retries`             | `int`                 | Max retries (default 3)                      |
| `final_answer`            | `str`                 | Formatted final response                     |
| `goal_achieved`           | `bool`                | Whether goal was met                         |
| `plan`                    | `Dict[str, Any]`      | Structured plan with objective + steps       |
| `executed_steps`          | `List[AgentStep]`     | Full execution trace                         |
| `pending_approvals`       | `List[PendingApproval]`| Approvals awaiting human input              |
| `errors`                  | `List[str]`           | Error messages from tools/nodes              |
| `corrections`             | `List[str]`           | Self-corrector adjustments applied           |
| `missing_info`            | `List[str]`           | Data gaps identified by planner              |
| `parallel_batches`        | `List[List[str]]`     | Batches of tools for parallel execution      |
| `retrieved_context`       | `str`                 | RAG context text                             |
| `evidence`                | `List[str]`           | Evidence strings from tools                  |
| `reasoning_summary`       | `str`                 | Verifier reasoning string                    |
| `remaining_uncertainty`   | `str`                 | Unresolved gaps                              |
| `provider_used`           | `str`                 | AI provider name                             |
| `model_used`              | `str`                 | Model name                                   |
| `execution_started_at`    | `str`                 | ISO timestamp                                |
| `execution_duration_ms`   | `float`               | Total execution time                         |
| `token_usage`             | `int`                 | Token count (future)                         |
| `tool_permission_levels`  | `Dict[str, str]`      | Permissions per tool                         |
| `approval_required`       | `bool`                | Global approval gate                         |
| `approval_id`             | `str`                 | Current approval identifier                  |
| `current_runbook`         | `str`                 | Active runbook name                          |
| `runbook_steps`           | `List[Dict]`          | Runbook step results                         |
| `risk_assessment`         | `Dict[str, Any]`      | RiskEngine output                            |
| `policy_results`          | `List[Dict]`          | PolicyEngine output per action               |
| `workflow_triggered`      | `str`                 | Matched workflow name                        |
| `scheduler_tasks`         | `List[Dict]`          | Pending scheduled tasks                      |
| `learnings`               | `List[Dict]`          | Learning records                             |
| `parallel_executions`     | `Dict[str, Any]`      | Results from parallel supervisor             |
| `approval_log`            | `List[Dict]`          | Historical approval decisions                |
| `agent_type`              | `str`                 | Multi-agent type (e.g., "operations")        |
| `agent_collaboration`     | `List[Dict]`          | Collaboration messages between agents        |
| `shared_state`            | `Dict[str, Any]`      | Shared state for multi-agent                 |
| `active_skills`           | `List[str]`           | Skill IDs matched to request                 |
| `skill_results`           | `List[Dict]`          | Results from skill execution                 |

---

## Tool Registry

Tools are registered in `src/intelligence/tools.py` as `Tool` objects with:

| Property           | Values                                   |
|--------------------|------------------------------------------|
| `name`             | Unique string identifier                 |
| `description`      | Human-readable description               |
| `category`         | `monitoring`, `containers`, `incidents`, `system`, `reports`, `notifications` |
| `risk_level`       | `none`, `low`, `medium`, `high`, `critical` |
| `access_mode`      | `read`, `write`                          |
| `permission_level` | `viewer`, `operator`, `admin`            |
| `requires_approval`| `bool`                                   |
| `destructive`      | `bool`                                   |

Tools are registered in `TOOL_REGISTRY` dict and governed by `RiskEngine` + `PolicyEngine`. The risk score determines auto-execution vs. human approval.

---

## Provider System

Five AI providers supported, configured via environment variables:

| Provider    | Env Prefix              | Key Variables                                    |
|-------------|-------------------------|--------------------------------------------------|
| OpenAI      | `AEGIS_AI_OPENAI_*`     | `API_KEY`, `MODEL`, `TEMPERATURE`, `MAX_TOKENS`  |
| Anthropic   | `AEGIS_AI_ANTHROPIC_*`  | `API_KEY`, `MODEL`, `BASE_URL`                   |
| Azure       | `AEGIS_AI_AZURE_*`      | `API_KEY`, `DEPLOYMENT`, `BASE_URL`              |
| Gemini      | `AEGIS_AI_GEMINI_*`     | `API_KEY`, `MODEL`                               |
| Ollama      | `AEGIS_AI_OLLAMA_*`     | `BASE_URL`, `MODEL`                              |

Default provider: `AEGIS_AI_PROVIDER=openai`. The factory (`src/intelligence/providers/factory.py`) instantiates the correct provider class.

---

## RAG Pipeline

```
Query ──▶ KnowledgeCollector ──▶ Source Documents
           │
           ├── collect_incidents()
           ├── collect_audit_logs()
           ├── collect_monitoring_history()
           ├── collect_reports()
           └── collect_runbooks()
               │
               ▼
        RetrievalResult (documents + context_text)
               │
               ▼
        Context Injection ──▶ LLM Generation ──▶ Answer
```

The `RAGEngine` (`src/intelligence/retrieval/rag.py`) collects context from incidents, audit logs, reports, monitoring history, and runbooks. Context is injected into the system prompt template.

---

## Memory Store

Six AI memory tables in a dedicated SQLite database (`ai_memory.db`):

| Table                  | Purpose                                           |
|------------------------|---------------------------------------------------|
| `ai_conversations`     | Full conversation history with confidence + goal   |
| `ai_incidents`         | AI-tracked incidents with severity + service       |
| `ai_recommendations`   | Recommendations generated by AI                    |
| `ai_remediations`      | Remediation actions taken                          |
| `ai_tool_executions`   | Per-tool execution records                         |
| `ai_learnings`         | Root cause → resolution patterns for self-improvement |

Managed by `SQLiteMemoryStore` (`src/intelligence/memory/sqlite_memory.py`).

---

## AI Skills

Five built-in skills registered via `SkillRegistry`:

| Skill ID                       | Name                | Tools Required        | Outputs                    |
|--------------------------------|---------------------|-----------------------|----------------------------|
| `builtin.system_analyzer`      | System Analyzer     | health, metrics       | `analysis_report`          |
| `builtin.incident_investigator`| Incident Investigator | incident, audit      | `investigation_report`     |
| `builtin.container_manager`    | Container Manager   | docker                | `container_status`, `actions_taken` |
| `builtin.report_generator`     | Report Generator    | report, metrics, incident | `formatted_report`      |
| `builtin.security_auditor`     | Security Auditor    | audit, target         | `security_audit_report`    |

Skills auto-select via keyword matching in `SkillEngine.auto_select_skills()`.

---

## Runbook Execution

```
YAML/JSON File ──▶ RunbookParser ──▶ RunbookDef ──▶ RunbookRegistry
                                                        │
                                                        ▼
                                                 RunbookEngine.execute()
                                                        │
                                              ┌─────────┼──────────┐
                                              ▼         ▼          ▼
                                        tool steps  wait steps  notify steps
                                              │
                                              ▼
                                        StepResult[] ──▶ RunbookResult
```

Runbooks support parallel step groups, conditions, retries, and approval gates.

---

## Policy Evaluation

Six default policies in `PolicyEngine`:

| Policy                            | Condition                                          | Effect               |
|-----------------------------------|-----------------------------------------------------|----------------------|
| `no-production-restart-business-hours` | business hours + environment=production       | deny                 |
| `require-approval-delete-target`   | always                                              | require_approval     |
| `max-restart-attempts`            | restart_count >= 3                                  | deny                 |
| `require-approval-destructive`    | destructive=True                                    | require_approval     |
| `max-retries-policy`              | retry_count >= 3                                    | deny                 |
| `approval-container-restart`      | environment=production                              | require_approval     |

---

## Risk Scoring

`RiskEngine` (`src/intelligence/risk.py`) scores per-tool and per-runbook on a 0–1 scale:

| Score Range | Level     | Auto-Execute | Requires Approval |
|-------------|-----------|--------------|-------------------|
| 0–0.1       | none      | Yes          | No                |
| 0.1–0.3     | low       | Yes          | No                |
| 0.3–0.5     | medium    | Conditional  | Yes               |
| 0.5–0.75    | high      | No           | Yes               |
| 0.75–1.0    | critical  | No           | Yes               |

Threshold configurable via `AEGIS_AI_AUTO_EXECUTE_THRESHOLD` (default 0.3).
