"""AegisNex Intelligence Engine — LangGraph-based agentic operations.

Architecture:
  - Model Provider Abstraction (providers/): Pluggable LLM backends
  - Memory Layer (memory/): Persistent conversation and operational memory
  - Retrieval Layer (retrieval/): RAG over incidents, audits, reports, runbooks
  - Tool Governance (tools.py): Registered tools with permissions and risk levels
  - State Machine (state.py, nodes.py, graph.py): LangGraph workflow
  - Execution History (history.py): Persisted workflow records
"""

from src.intelligence.graph import (
    get_workflows,
    reset_graph,
    run_analyze,
    run_chat,
    run_plan,
    run_workflow,
)
from src.intelligence.history import (
    get_history_count,
    get_history_stats,
    list_history,
    save_workflow,
)
from src.intelligence.memory import SQLiteMemoryStore
from src.intelligence.providers import ModelProvider, create_provider, get_provider_names
from src.intelligence.retrieval import KnowledgeCollector, RAGEngine
from src.intelligence.state import AgentState, initial_state
from src.intelligence.tools import (
    TOOL_REGISTRY,
    execute_tool,
    get_tool,
    list_tool_definitions,
    list_tools,
)

__all__ = [
    "TOOL_REGISTRY",
    "AgentState",
    "KnowledgeCollector",
    "ModelProvider",
    "RAGEngine",
    "SQLiteMemoryStore",
    "create_provider",
    "execute_tool",
    "get_history_count",
    "get_history_stats",
    "get_provider_names",
    "get_tool",
    "get_workflows",
    "initial_state",
    "list_history",
    "list_tool_definitions",
    "list_tools",
    "reset_graph",
    "run_analyze",
    "run_chat",
    "run_plan",
    "run_workflow",
    "save_workflow",
]
