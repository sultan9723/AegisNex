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
    run_workflow,
    run_chat,
    run_analyze,
    run_plan,
    reset_graph,
    get_workflows,
)
from src.intelligence.history import save_workflow, list_history, get_history_count, get_history_stats
from src.intelligence.tools import (
    TOOL_REGISTRY,
    list_tools,
    list_tool_definitions,
    get_tool,
    execute_tool,
)
from src.intelligence.state import AgentState, initial_state
from src.intelligence.memory import SQLiteMemoryStore
from src.intelligence.retrieval import RAGEngine, KnowledgeCollector
from src.intelligence.providers import ModelProvider, create_provider, get_provider_names

__all__ = [
    "run_workflow",
    "run_chat",
    "run_analyze",
    "run_plan",
    "reset_graph",
    "get_workflows",
    "save_workflow",
    "list_history",
    "get_history_count",
    "get_history_stats",
    "TOOL_REGISTRY",
    "list_tools",
    "list_tool_definitions",
    "get_tool",
    "execute_tool",
    "AgentState",
    "initial_state",
    "SQLiteMemoryStore",
    "RAGEngine",
    "KnowledgeCollector",
    "ModelProvider",
    "create_provider",
    "get_provider_names",
]
