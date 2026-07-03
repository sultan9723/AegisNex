"""Structured execution logging for LangGraph nodes.

Every node produces ExecutionLog entries that are stored in AgentState.executed_steps.
Logs include: node name, execution time, inputs, outputs, errors, tool calls, execution ID, correlation ID.
"""

from __future__ import annotations

import functools
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


def utc_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def generate_execution_id() -> str:
    """Generate a unique execution ID (UUID4)."""
    return str(uuid.uuid4())


@dataclass
class ExecutionLog:
    """Structured execution log for a LangGraph node.
    
    Records complete execution context including timing, inputs, outputs,
    errors, and tool invocations. Supports correlation for tracing across nodes.
    """
    
    node_name: str
    """Name of the LangGraph node that produced this log"""
    
    execution_id: str
    """Unique ID for this node execution"""
    
    correlation_id: str
    """ID to correlate logs across multiple nodes in a single workflow"""
    
    start_time: str
    """UTC timestamp when execution started (ISO 8601)"""
    
    end_time: str
    """UTC timestamp when execution completed (ISO 8601)"""
    
    duration_ms: float
    """Total execution time in milliseconds"""
    
    execution_status: str
    """Status: 'success', 'warning', 'error', 'skipped'"""
    
    input_data: Dict[str, Any] = field(default_factory=dict)
    """Input to the node (subset of AgentState)"""
    
    output_data: Dict[str, Any] = field(default_factory=dict)
    """Output from the node (state modifications)"""
    
    errors: List[str] = field(default_factory=list)
    """List of error messages encountered during execution"""
    
    warnings: List[str] = field(default_factory=list)
    """List of warning messages during execution"""
    
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    """List of tools invoked during this node's execution"""
    
    decision_log: List[Dict[str, Any]] = field(default_factory=list)
    """Detailed decision log (e.g., routing decisions, policy checks)"""
    
    context: Dict[str, Any] = field(default_factory=dict)
    """Additional context-specific data for this node"""

    def to_dict(self) -> Dict[str, Any]:
        """Convert execution log to dictionary."""
        return asdict(self)

    def to_agent_step(self) -> Dict[str, Any]:
        """Convert to AgentStep format for state.executed_steps."""
        return {
            "node": self.node_name,
            "status": self.execution_status,
            "detail": f"{self.node_name} execution: {self.duration_ms:.2f}ms",
            "timestamp": self.end_time,
            "data": {
                "execution_log": self.to_dict(),
            },
        }

    @property
    def summary(self) -> str:
        """Brief summary of execution."""
        error_count = len(self.errors)
        warning_count = len(self.warnings)
        tool_count = len(self.tool_calls)
        
        parts = [f"{self.node_name} ({self.execution_status})"]
        if tool_count > 0:
            parts.append(f"tools={tool_count}")
        if error_count > 0:
            parts.append(f"errors={error_count}")
        if warning_count > 0:
            parts.append(f"warnings={warning_count}")
        parts.append(f"{self.duration_ms:.2f}ms")
        
        return " ".join(parts)


class ExecutionLogger:
    """Context manager for structured node execution logging."""

    def __init__(
        self,
        node_name: str,
        correlation_id: Optional[str] = None,
    ):
        """Initialize execution logger.
        
        Args:
            node_name: Name of the LangGraph node
            correlation_id: Optional ID to correlate logs across nodes
        """
        self.node_name = node_name
        self.correlation_id = correlation_id or generate_execution_id()
        self.execution_id = generate_execution_id()
        self.start_time = utc_now()
        self.end_time = ""
        self.start_timestamp = time.time()
        
        self.input_data: Dict[str, Any] = {}
        self.output_data: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.decision_log: List[Dict[str, Any]] = []
        self.context: Dict[str, Any] = {}

    def add_input(self, data: Dict[str, Any]) -> None:
        """Record input to the node."""
        self.input_data = data.copy() if data else {}

    def add_output(self, data: Dict[str, Any]) -> None:
        """Record output from the node."""
        self.output_data = data.copy() if data else {}

    def add_error(self, error: str) -> None:
        """Record an error that occurred during execution."""
        if error:
            self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Record a warning that occurred during execution."""
        if warning:
            self.warnings.append(warning)

    def add_tool_call(
        self,
        tool_name: str,
        status: str,
        input_params: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record a tool invocation.
        
        Args:
            tool_name: Name of the tool
            status: Status of the call ('pending', 'success', 'error')
            input_params: Parameters passed to the tool
            output: Output from the tool
            error: Error message if the call failed
        """
        call = {
            "tool_name": tool_name,
            "status": status,
            "timestamp": utc_now(),
        }
        if input_params:
            call["input_params"] = input_params
        if output:
            call["output"] = output
        if error:
            call["error"] = error
        
        self.tool_calls.append(call)

    def add_decision(
        self,
        decision_type: str,
        decision: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a decision made by the node.
        
        Args:
            decision_type: Type of decision (e.g., 'routing', 'policy_check')
            decision: The decision made
            reason: Reason for the decision
            metadata: Additional metadata about the decision
        """
        entry = {
            "type": decision_type,
            "decision": decision,
            "reason": reason,
            "timestamp": utc_now(),
        }
        if metadata:
            entry["metadata"] = metadata
        
        self.decision_log.append(entry)

    def add_context(self, key: str, value: Any) -> None:
        """Add context-specific data."""
        self.context[key] = value

    def __enter__(self) -> ExecutionLogger:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and finalize log."""
        self.end_time = utc_now()

    def finalize(self, execution_status: str = "success") -> ExecutionLog:
        """Create final ExecutionLog entry.
        
        Args:
            execution_status: Final execution status
            
        Returns:
            Completed ExecutionLog entry
        """
        if not self.end_time:
            self.end_time = utc_now()
        
        duration_ms = (time.time() - self.start_timestamp) * 1000
        
        return ExecutionLog(
            node_name=self.node_name,
            execution_id=self.execution_id,
            correlation_id=self.correlation_id,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=duration_ms,
            execution_status=execution_status,
            input_data=self.input_data,
            output_data=self.output_data,
            errors=self.errors,
            warnings=self.warnings,
            tool_calls=self.tool_calls,
            decision_log=self.decision_log,
            context=self.context,
        )


class ExecutionLogCollector:
    """Collects execution logs from all nodes in a workflow."""

    def __init__(self, correlation_id: Optional[str] = None):
        """Initialize log collector.
        
        Args:
            correlation_id: ID to correlate logs across nodes
        """
        self.correlation_id = correlation_id or generate_execution_id()
        self.logs: List[ExecutionLog] = []

    def get_logger(self, node_name: str) -> ExecutionLogger:
        """Create an execution logger for a node.
        
        Args:
            node_name: Name of the node
            
        Returns:
            ExecutionLogger configured for this node
        """
        return ExecutionLogger(node_name, self.correlation_id)

    def add_log(self, log: ExecutionLog) -> None:
        """Add a completed execution log."""
        self.logs.append(log)

    def get_logs(self) -> List[ExecutionLog]:
        """Get all collected logs."""
        return self.logs.copy()

    def get_log_summary(self) -> Dict[str, Any]:
        """Get summary of all collected logs.
        
        Returns:
            Dictionary with execution summary
        """
        total_duration_ms = sum(log.duration_ms for log in self.logs)
        total_errors = sum(len(log.errors) for log in self.logs)
        total_warnings = sum(len(log.warnings) for log in self.logs)
        total_tool_calls = sum(len(log.tool_calls) for log in self.logs)
        
        return {
            "correlation_id": self.correlation_id,
            "node_count": len(self.logs),
            "total_duration_ms": total_duration_ms,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "total_tool_calls": total_tool_calls,
            "logs": [log.to_dict() for log in self.logs],
        }

    def to_executed_steps(self) -> List[Dict[str, Any]]:
        """Convert all logs to AgentStep format."""
        return [log.to_agent_step() for log in self.logs]


# Helper functions for node instrumentation

def get_correlation_id(state: Dict[str, Any]) -> str:
    """Get or generate correlation ID from state."""
    correlation_id = state.get("_correlation_id")
    if not correlation_id:
        correlation_id = generate_execution_id()
        state["_correlation_id"] = correlation_id
    return correlation_id


def add_execution_log_to_state(state: Dict[str, Any], log: ExecutionLog) -> None:
    """Add an execution log to state.executed_steps as an AgentStep.
    
    Args:
        state: The AgentState dictionary
        log: The ExecutionLog to add
    """
    executed_steps = list(state.get("executed_steps", []))
    executed_steps.append(log.to_agent_step())
    state["executed_steps"] = executed_steps


def create_logger_for_state(node_name: str, state: Dict[str, Any]) -> ExecutionLogger:
    """Create an execution logger configured for a state.
    
    Args:
        node_name: Name of the node
        state: The AgentState
        
    Returns:
        Configured ExecutionLogger
    """
    correlation_id = get_correlation_id(state)
    return ExecutionLogger(node_name, correlation_id)
