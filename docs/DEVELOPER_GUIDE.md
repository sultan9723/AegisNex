# Developer Guide

## Project Structure

```
F:\AegisNex\
├── docs/                        # Documentation
├── src/
│   ├── dashboard.py             # FastAPI app, routes, WebSocket
│   ├── platform_db.py           # PlatformRepository (SQLite/PostgreSQL)
│   ├── intelligence/            # AI Engine (LangGraph)
│   │   ├── graph.py             # StateGraph construction
│   │   ├── nodes.py             # 12 workflow nodes
│   │   ├── tools.py             # Tool registry
│   │   ├── risk.py              # RiskEngine
│   │   ├── policy.py            # PolicyEngine
│   │   ├── providers/           # AI provider factory (5 providers)
│   │   ├── memory/              # SQLiteMemoryStore (6 tables)
│   │   ├── retrieval/           # RAG pipeline
│   │   ├── runbooks/            # Runbook parser + registry
│   │   ├── workflows/           # Workflow definitions
│   │   └── scheduler/           # Task scheduler
│   ├── agents/                  # Multi-agent system
│   │   ├── orchestrator.py      # AgentOrchestrator
│   │   ├── supervisors.py       # 4 concrete supervisors
│   │   ├── state.py             # SharedAgentState
│   │   └── base.py              # BaseAgent
│   ├── integrations/            # 11 integration providers
│   ├── plugins/                 # Plugin system
│   ├── skills/                  # AI skills
│   ├── compliance/              # Compliance frameworks
│   ├── search/                  # Enterprise search
│   ├── telemetry/               # Telemetry collector
│   ├── multitenant/             # Multi-tenant models
│   └── workflow_designer/       # Visual workflow builder
├── tests/                       # Test suite
├── data/                        # Runtime data
├── logs/                        # Log files
└── requirements.txt             # Python dependencies
```

---

## Development Setup

```powershell
# Clone
git clone <repo-url> aegisnex
cd aegisnex

# Create virtual env
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install deps
pip install -r requirements.txt

# Install dev extras
pip install pytest pytest-asyncio pytest-cov mypy ruff

# Copy env
copy .env.example .env
# Edit .env with your settings

# Init DB
python -m src.scripts.init_db

# Run dev server
python -m uvicorn src.dashboard:app --reload --port 8000
```

---

## Coding Conventions

### Python Style

| Rule                | Standard                              |
|---------------------|---------------------------------------|
| **Formatter**       | `ruff format`                         |
| **Linter**          | `ruff check`                          |
| **Type checker**    | `mypy --strict`                       |
| **Line length**     | 120 characters                        |
| **Imports**         | `from __future__ import annotations`  |
| **Type annotations**| Required on all public functions      |
| **Docstrings**      | Google style for public APIs          |

### Naming

| Element         | Convention       | Example                  |
|-----------------|------------------|--------------------------|
| Classes         | PascalCase       | `PlatformRepository`     |
| Functions       | snake_case       | `execute_tool()`         |
| Variables       | snake_case       | `current_plan`           |
| Constants       | UPPER_SNAKE      | `TOOL_REGISTRY`          |
| Private methods | `_` prefix       | `_metrics_tool()`        |
| Enums           | PascalCase       | `RiskLevel`              |
| Enum values     | UPPER_SNAKE      | `RiskLevel.CRITICAL`     |

---

## Working with the AI Engine

### AgentState

The `AgentState` TypedDict is the central state object for all LangGraph workflows:

```python
from typing import TypedDict, NotRequired
from typing import Any, Dict, List, Optional

class AgentState(TypedDict):
    input: str
    user_id: str
    organization_id: str
    project_id: NotRequired[str]
    session_id: str
    conversation_id: str
    objective: str
    current_plan: List[Dict[str, Any]]
    parallel_batches: List[List[Dict[str, Any]]]
    completed_tools: List[str]
    tool_results: Dict[str, Any]
    active_skills: List[str]
    skill_results: Dict[str, Any]
    current_runbook: NotRequired[str]
    runbook_steps: List[Dict[str, Any]]
    workflow_triggered: bool
    runbook_triggered: bool
    missing_info: List[str]
    context: Dict[str, Any]
    vector_results: List[Dict[str, Any]]
    policy_results: List[Dict[str, Any]]
    risk_assessment: NotRequired[Dict[str, Any]]
    approval_required: bool
    pending_approvals: List[Dict[str, Any]]
    goal_achieved: bool
    final_answer: str
    errors: List[str]
    conversation_history: List[Dict[str, Any]]
    iterations: int
    max_iterations: int
    reasoning_summary: str
    remaining_uncertainty: str
    observations: List[str]
    evidence: List[str]
    learnings: List[str]
    scheduler_tasks: List[Dict[str, Any]]
```

### Running a Workflow

```python
from src.intelligence.graph import run_workflow

result = run_workflow(
    user_input="investigate high CPU on production",
    user_id="user-1",
    organization_id="org-1",
    session_id="sess-1",
    conversation_id="conv-1",
)
print(result["final_answer"])
```

### Adding a New Node

1. Add the implementation in `src/intelligence/nodes.py`:

```python
def my_custom_node(state: AgentState) -> Dict[str, Any]:
    # Process state and return updates
    return {"observations": ["Custom processing complete"]}
```

2. Add to the graph in `src/intelligence/graph.py`:

```python
workflow.add_node("my_custom_node", my_custom_node)
workflow.add_edge("previous_node", "my_custom_node")
workflow.add_conditional_edges("my_custom_node", router_func, {...})
```

---

## Registering a New Tool

1. **Implement** in `src/intelligence/tools.py`:

```python
def _my_tool(repo: Optional[PlatformRepository] = None, **kwargs: Any) -> Dict[str, Any]:
    try:
        # Tool logic here
        return {"status": "ok", "data": result}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
```

2. **Register** in `TOOL_REGISTRY`:

```python
TOOL_REGISTRY["my_tool"] = Tool(
    "my_tool",
    "Description of my tool",
    "my_category",
    _my_tool,
    permission_level=PermissionLevel.OPERATOR,
    access_mode=AccessMode.READ,
    risk_level=RiskLevel.LOW,
)
```

3. **Add definition** to `TOOL_DEFINITIONS` for governance.

4. **Add parameters** schema.

5. **Expose via API** if needed — add route in `src/dashboard.py`.

---

## Creating a Custom Integration

Integrations reside in `src/integrations/providers/`. Each provider extends a base pattern:

```python
# src/integrations/providers/my_provider.py
from src.integrations.base import IntegrationProvider

class MyProvider(IntegrationProvider):
    def __init__(self, config: dict):
        self.api_key = config["api_key"]
        self.base_url = config["base_url"]

    async def health_check(self) -> dict:
        # Check connectivity
        return {"status": "ok", "latency_ms": 42}

    async def execute_action(self, action: str, params: dict) -> dict:
        # Execute provider-specific action
        ...
```

Register in `src/integrations/__init__.py` and add config schema in the settings UI.

---

## Writing Tests

### Test Framework

Tests use `pytest` with `pytest-asyncio` for async tests.

```powershell
# Run all tests
pytest

# Run specific module
pytest tests/test_intelligence.py -v

# Run with coverage
pytest --cov=src --cov-report=html
```

### Test Patterns

```python
import pytest
from src.intelligence.tools import execute_tool

def test_metrics_tool_returns_data():
    result = execute_tool("metrics")
    assert "metrics" in result
    assert result["status"] == "ok"

@pytest.mark.asyncio
async def test_workflow_execution():
    from src.intelligence.graph import run_workflow
    result = run_workflow("test query", "user-1", "org-1", "sess-1", "conv-1")
    assert "final_answer" in result
```

### Mocking the AI Provider

```python
from unittest.mock import patch

@pytest.mark.asyncio
async def test_planner_with_mock_llm():
    with patch("src.intelligence.providers.factory.LLMFactory.create") as mock:
        mock.return_value.invoke.return_value = {"plan": [...]}
        result = run_workflow("test", "user-1", "org-1", "sess-1", "conv-1")
        assert result["goal_achieved"]
```

---

## Plugin Development

### Plugin Structure

```python
from src.plugins.base import AegisNexPlugin

class MyPlugin(AegisNexPlugin):
    @property
    def name(self) -> str:
        return "my-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def on_load(self, context: dict) -> None:
        # Initialize plugin resources
        pass

    async def on_unload(self) -> None:
        # Cleanup
        pass

    async def execute_hook(self, hook_name: str, data: dict) -> dict:
        # Handle hook invocation
        return {"status": "ok"}
```

### Plugin Hooks

| Hook Name              | Trigger                              |
|------------------------|--------------------------------------|
| `before_tool_execute`  | Before any tool execution            |
| `after_tool_execute`   | After tool execution                 |
| `before_workflow`      | Before workflow starts               |
| `after_workflow`       | After workflow completes             |
| `on_incident_created`  | When a new incident is created       |
| `on_notification_send` | Before a notification is sent        |

---

## API Extensions

Add new route groups in `src/dashboard.py`:

```python
@router.get("/api/my-feature")
async def my_feature_endpoint(
    request: Request,
    repo: PlatformRepository = Depends(get_repository),
    current_user: dict = Depends(require_auth),
):
    return {"data": await repo.my_feature()}
```

--- 

## Building the Frontend

```powershell
cd frontend
npm install
npm run dev    # Development server on port 5173
npm run build  # Production build -> dist/
```

The frontend serves static files at `/` and is proxied to the FastAPI backend.

---

## Running Pre-Commit Checks

```powershell
# Before committing, run:
ruff format .              # Format code
ruff check --fix .        # Lint + auto-fix
mypy src/                 # Type checking
pytest                    # Tests
```

---

## Common Development Tasks

| Task                          | Command                                              |
|-------------------------------|------------------------------------------------------|
| Reset dev database            | `Remove-Item .\data\aegisnex.db; python -m src.scripts.init_db` |
| Add database migration        | Create new migration in `src/scripts/migrations/`    |
| Create new AI skill           | Add class in `src/skills/builtin.py`, register in `SkillEngine` |
| Add compliance framework      | Add class in `src/compliance/frameworks.py`          |
| Create custom workflow node   | Add type to `src/workflow_designer/models.py`, handler in `src/intelligence/nodes.py` |
| Add new notification channel  | Implement in `notifications/channels/`, register in channel factory |
| Add new runbook               | Add `.yaml` file to `src/intelligence/runbooks/library/` |

---

## Generating Documentation

Documentation is maintained manually in `docs/`. Each file follows the same Markdown format with:

- Title and purpose
- Tables for structured data
- Code blocks for commands and examples
- Cross-references to source files (`src/path/file.py:line`)
