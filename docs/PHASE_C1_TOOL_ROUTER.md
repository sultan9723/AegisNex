# Phase C1: Tool Router Implementation

## Overview

Phase C1 introduces the **Explicit Tool Router** to the AegisNex Intelligence Engine. The router maps abstract tasks from the Planner to concrete tools from the Tool Registry without executing them.

## Architecture

### Graph Flow (Updated)

```
User Request
    ↓
Planner (outputs abstract tasks)
    ↓
Tool Router (NEW) - Maps tasks to tools
    ↓
Tool Executor (executes routed tools)
    ↓
Verifier
    ↓
Self-Corrector
    ↓
Goal Evaluator
    ↓
Final Response
```

## Implementation Details

### 1. Tool Router Module (`src/intelligence/tool_router.py`)

**New Classes:**
- `ToolRouterConfig`: Configuration for router behavior (logger, strict_mode)
- `ToolRouterDecision`: Represents a single routing decision with metadata
- `ToolRouter`: Main router that maps tasks to tools

**Key Methods:**
- `route_task(task_name)`: Route a single task to a tool
- `route_plan(plan)`: Route all tasks in a plan
- `get_tool_metadata(tool_name)`: Retrieve tool metadata
- `get_routing_log()`: Get complete routing decision log
- `clear_decisions()`: Reset routing history

**Features:**
- ✓ Validates tasks exist in Tool Registry
- ✓ Logs every routing decision (INFO level)
- ✓ Returns tool metadata (category, risk level, permissions)
- ✓ Never executes tools
- ✓ Never accesses database
- ✓ Handles invalid tasks gracefully (strict_mode=False by default)
- ✓ Enriches state with routing context

### 2. Router Node (`src/intelligence/nodes.py`)

**New Function:** `tool_router_node(state: AgentState) -> AgentState`

**Responsibilities:**
- Reads `current_plan` from AgentState
- Uses ToolRouter to map tasks to tools
- Updates `current_plan` to only include routed tools
- Filters `parallel_batches` to match routed tools
- Appends routing step to `executed_steps`
- Populates `tool_router_results` with:
  - `timestamp`: Routing execution time
  - `total_tasks`: Number of tasks in plan
  - `routed_tools`: Successfully routed tool names
  - `invalid_tasks`: Tasks not found in registry
  - `decisions`: Complete routing decision log
  - `tool_metadata`: Enriched metadata for each tool

**State Updates:**
- ✓ `state['current_plan']` - filtered to valid tools only
- ✓ `state['parallel_batches']` - filtered to match valid tools
- ✓ `state['tool_router_results']` - routing results and metadata
- ✓ `state['executed_steps']` - appends routing step with details
- ✓ `state['errors']` - records any invalid tasks (non-fatal)

### 3. Graph Integration (`src/intelligence/graph.py`)

**Changes:**
- Added import: `tool_router_node`
- Added node: `graph.add_node("tool_router", tool_router_node)`
- Updated planner_router: routes to `"route"` instead of `"execute"` when plan exists
- Added edge: `"tool_router" → "tool_executor"`
- Updated graph documentation

**New Graph Path:**
```python
"planner" → "tool_router" → "tool_executor" → "verifier" → ...
```

### 4. State Extension (`src/intelligence/state.py`)

**Added Field:**
```python
tool_router_results: Dict[str, Any]
```

**Initialized as:** `{}`

## Tool Registry Integration

The router uses the existing Tool Registry from `src/intelligence/tools.py`:

**Available Tools (8):**
1. `metrics` - System metrics (CPU, memory, disk, network)
2. `docker` - Docker container status
3. `incident` - Incident management queries
4. `target` - Monitoring targets
5. `audit` - Audit log entries
6. `report` - Operational reports
7. `notification` - Notification status
8. `health` - System health checks

All tools are READ-ONLY with `risk_level=none` and `permission_level=viewer`.

## Logging

### Router Logging (INFO Level)

Every routing decision is logged:
```
tool_router - Routing decision: task=metrics, tool=metrics, category=monitoring, risk=none
tool_router - Plan routing complete: total=4, routed=4, invalid=0
```

### Node Logging (executed_steps)

Router step recorded with metadata:
```json
{
  "node": "tool_router",
  "status": "completed",
  "detail": "Routed 4/4 tasks",
  "timestamp": "2026-07-01T12:00:00Z",
  "data": {
    "total": 4,
    "routed": 4,
    "invalid": 0,
    "routing_log": [...]
  }
}
```

## Test Coverage

**Test Suite:** `tests/test_tool_router.py`

**5 Tests - All Passing:**
1. ✓ `test_tool_router_basic` - Basic routing of valid tasks
2. ✓ `test_tool_router_with_invalid_tasks` - Graceful handling of invalid tasks
3. ✓ `test_tool_router_metadata` - Tool metadata retrieval
4. ✓ `test_tool_router_node` - Router node in LangGraph state
5. ✓ `test_tool_router_logging` - Routing decision logging

## Usage Example

```python
from src.intelligence.tool_router import ToolRouter, ToolRouterConfig
import logging

# Create router with logging
config = ToolRouterConfig(
    logger=logging.getLogger("my_router"),
    strict_mode=False  # Skip invalid tasks instead of failing
)
router = ToolRouter(config=config)

# Route a plan
plan = ["metrics", "docker", "invalid_tool", "health"]
result = router.route_plan(plan)

# Result contains:
# {
#   "success": True,
#   "total_tasks": 4,
#   "routed_tools": ["metrics", "docker", "health"],
#   "invalid_tasks": ["invalid_tool"],
#   "decisions": [...],
#   "timestamp": "2026-07-01T..."
# }

# Get routing log
decisions = router.get_routing_log()
for decision in decisions:
    print(f"{decision['tool_name']}: {decision['reason']}")
```

## Backward Compatibility

✓ **No Breaking Changes**
- Planner node unchanged
- Tool Executor node unchanged
- LangGraph routing logic extended (not replaced)
- Existing APIs unmodified
- Frontend unaffected
- Dashboard unaffected
- MCP unaffected
- Docker monitoring unaffected
- Authentication unchanged

## Design Principles Followed

✓ **Modularity**: Router is standalone, reusable module
✓ **Single Responsibility**: Router only routes, never executes
✓ **Dependency Injection**: No hardcoded dependencies
✓ **Logging**: Every decision logged with context
✓ **State Immutability**: Creates new state, doesn't mutate
✓ **Read-Only Operations**: No database access, no tool execution
✓ **Error Handling**: Graceful handling of invalid tasks

## Files Modified

1. **Created:**
   - `src/intelligence/tool_router.py` (180 lines)
   - `tests/test_tool_router.py` (150 lines)

2. **Modified:**
   - `src/intelligence/nodes.py` - Added import, tool_router_node function
   - `src/intelligence/graph.py` - Updated imports, added node, updated routing
   - `src/intelligence/state.py` - Added tool_router_results field

## Next Steps (Not Implemented in C1)

Phase C1 completes the Tool Router. Future phases may include:
- Phase C2: Reflection & Goal Verification node
- Phase C3: Enhanced error handling and recovery
- Phase C4: Skill-based task routing
- Phase C5: Performance optimization

---

**Status:** ✓ Complete
**Tests:** ✓ 5/5 Passing
**Backward Compatible:** ✓ Yes
**Ready for Review:** ✓ Yes
