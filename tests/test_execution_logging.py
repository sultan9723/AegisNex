"""Test for Phase C2: Structured Node Execution Logging"""

from src.intelligence.execution_logger import (
    ExecutionLogger,
    ExecutionLog,
    create_logger_for_state,
    add_execution_log_to_state,
    get_correlation_id,
)
from src.intelligence.nodes import (
    plan_node,
    tool_router_node,
    tool_executor_node,
    verifier_node,
    goal_evaluator_node,
)
from src.intelligence.state import initial_state
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_execution_logger_basic():
    """Test basic ExecutionLogger functionality."""
    print("\n=== Test 1: ExecutionLogger Basic ===")
    
    exec_logger = ExecutionLogger("test_node", "corr-123")
    
    assert exec_logger.node_name == "test_node"
    assert exec_logger.correlation_id == "corr-123"
    assert exec_logger.execution_id != ""
    
    # Add data
    exec_logger.add_input({"key": "value"})
    exec_logger.add_output({"result": "data"})
    exec_logger.add_error("Test error")
    exec_logger.add_warning("Test warning")
    exec_logger.add_tool_call("tool1", "success", output={"status": "ok"})
    exec_logger.add_decision("routing", "decision1", "Test decision")
    
    # Finalize
    log = exec_logger.finalize("success")
    
    assert log.node_name == "test_node"
    assert log.execution_status == "success"
    assert len(log.errors) == 1
    assert len(log.warnings) == 1
    assert len(log.tool_calls) == 1
    assert len(log.decision_log) == 1
    assert log.summary != ""
    
    print(f"✓ Log created: {log.summary}")
    print("✓ Test 1 passed")


def test_execution_log_to_agent_step():
    """Test conversion of ExecutionLog to AgentStep format."""
    print("\n=== Test 2: ExecutionLog to AgentStep ===")
    
    exec_logger = ExecutionLogger("planner", "corr-456")
    exec_logger.add_input({"request": "test"})
    exec_logger.add_output({"plan": ["tool1", "tool2"]})
    log = exec_logger.finalize("success")
    
    agent_step = log.to_agent_step()
    
    assert agent_step["node"] == "planner"
    assert agent_step["status"] == "success"
    assert "execution_log" in agent_step["data"]
    assert agent_step["timestamp"] != ""
    
    print(f"AgentStep: {agent_step}")
    print("✓ Test 2 passed")


def test_correlation_id_propagation():
    """Test that correlation IDs are propagated across nodes."""
    print("\n=== Test 3: Correlation ID Propagation ===")
    
    state = initial_state("test request")
    
    # Get correlation ID
    corr_id = get_correlation_id(state)
    assert corr_id != ""
    
    # Get it again - should be same
    corr_id2 = get_correlation_id(state)
    assert corr_id == corr_id2
    
    print(f"Correlation ID: {corr_id}")
    print("✓ Test 3 passed")


def test_planner_node_logging():
    """Test Planner node produces structured logs."""
    print("\n=== Test 4: Planner Node Logging ===")
    
    state = initial_state("check system health")
    executed_steps_before = len(state.get("executed_steps", []))
    
    # Run planner
    result_state = plan_node(state)
    
    # Check state was updated
    assert result_state["objective"] != ""
    assert len(result_state["current_plan"]) > 0
    
    # Check execution log was added
    executed_steps_after = len(result_state["executed_steps"])
    assert executed_steps_after > executed_steps_before
    
    # Check log contains execution_log
    planner_steps = [s for s in result_state["executed_steps"] if s["node"] == "planner"]
    assert len(planner_steps) > 0
    planner_log = planner_steps[-1]
    assert "execution_log" in planner_log["data"]
    
    exec_log = planner_log["data"]["execution_log"]
    assert "node_name" in exec_log
    assert "execution_id" in exec_log
    assert "correlation_id" in exec_log
    assert "start_time" in exec_log
    assert "end_time" in exec_log
    assert "duration_ms" in exec_log
    assert "input_data" in exec_log
    assert "output_data" in exec_log
    assert "decision_log" in exec_log
    
    print(f"Execution log fields: {list(exec_log.keys())}")
    print(f"Duration: {exec_log['duration_ms']:.2f}ms")
    print(f"Input data: {exec_log['input_data']}")
    print(f"Decisions made: {len(exec_log['decision_log'])}")
    print("✓ Test 4 passed")


def test_router_node_logging():
    """Test Router node produces structured logs."""
    print("\n=== Test 5: Router Node Logging ===")
    
    state = initial_state("analyze metrics")
    state["objective"] = "Investigate system metrics"
    state["current_plan"] = ["metrics", "docker", "health", "invalid_tool"]
    state["parallel_batches"] = [["metrics", "health"], ["docker"], ["invalid_tool"]]
    
    executed_steps_before = len(state.get("executed_steps", []))
    
    # Run router
    result_state = tool_router_node(state)
    
    # Check routing filtered invalid tool
    assert "invalid_tool" not in result_state["current_plan"]
    assert result_state["current_plan"] == ["metrics", "docker", "health"]
    
    # Check execution log was added
    executed_steps_after = len(result_state["executed_steps"])
    assert executed_steps_after > executed_steps_before
    
    # Check log
    router_steps = [s for s in result_state["executed_steps"] if s["node"] == "tool_router"]
    assert len(router_steps) > 0
    router_log = router_steps[-1]["data"]["execution_log"]
    
    assert router_log["node_name"] == "tool_router"
    assert "correlation_id" in router_log
    assert len(router_log["decision_log"]) > 0
    assert len(router_log["tool_calls"]) == 0  # Router doesn't execute tools
    
    print(f"Routed tools: {router_log['output_data']['routed_tools']}")
    print(f"Invalid tasks: {router_log['output_data']['invalid_tasks']}")
    print(f"Routing decisions: {len(router_log['decision_log'])}")
    print("✓ Test 5 passed")


def test_executor_node_logging():
    """Test Executor node produces structured logs with tool calls."""
    print("\n=== Test 6: Executor Node Logging ===")
    
    state = initial_state("check docker")
    state["current_plan"] = ["docker"]
    state["parallel_batches"] = [["docker"]]
    
    # Run executor
    result_state = tool_executor_node(state)
    
    # Check execution log
    executor_steps = [s for s in result_state["executed_steps"] if s["node"] == "tool_executor"]
    assert len(executor_steps) > 0
    executor_log = executor_steps[-1]["data"]["execution_log"]
    
    assert executor_log["node_name"] == "tool_executor"
    assert len(executor_log["tool_calls"]) > 0
    assert executor_log["output_data"]["tools_executed"] > 0
    
    # Check tool call structure
    tool_call = executor_log["tool_calls"][0]
    assert "tool_name" in tool_call
    assert "status" in tool_call
    assert "timestamp" in tool_call
    
    print(f"Tools executed: {executor_log['output_data']['tools_executed']}")
    print(f"Tool calls logged: {len(executor_log['tool_calls'])}")
    print(f"Tool call example: {tool_call}")
    print("✓ Test 6 passed")


def test_verifier_node_logging():
    """Test Verifier node produces structured logs."""
    print("\n=== Test 7: Verifier Node Logging ===")
    
    state = initial_state("check health")
    state["current_plan"] = ["docker", "health"]
    state["tool_results"] = {
        "docker": {"status": "ok", "count": 5},
        "health": {"status": "ok", "count": 3},
    }
    
    # Run verifier
    result_state = verifier_node(state)
    
    # Check execution log
    verifier_steps = [s for s in result_state["executed_steps"] if s["node"] == "verifier"]
    assert len(verifier_steps) > 0
    verifier_log = verifier_steps[-1]["data"]["execution_log"]
    
    assert verifier_log["node_name"] == "verifier"
    assert "confidence" in verifier_log["output_data"]
    assert len(verifier_log["decision_log"]) > 0
    
    print(f"Confidence: {verifier_log['output_data']['confidence']:.0%}")
    print(f"Verification decisions: {len(verifier_log['decision_log'])}")
    print(f"Observations: {verifier_log['output_data']['observations_count']}")
    print("✓ Test 7 passed")


def test_goal_evaluator_node_logging():
    """Test Goal Evaluator node produces structured logs."""
    print("\n=== Test 8: Goal Evaluator Node Logging ===")
    
    state = initial_state("analyze system")
    state["objective"] = "System analysis"
    state["tool_results"] = {
        "metrics": {"status": "ok", "count": 10},
        "docker": {"status": "ok", "count": 5},
    }
    state["confidence"] = 0.85
    state["observations"] = ["System is healthy"]
    state["reasoning_summary"] = "All tools executed successfully"
    
    # Run goal evaluator
    result_state = goal_evaluator_node(state)
    
    # Check execution log
    goal_steps = [s for s in result_state["executed_steps"] if s["node"] == "goal_evaluator"]
    assert len(goal_steps) > 0
    goal_log = goal_steps[-1]["data"]["execution_log"]
    
    assert goal_log["node_name"] == "goal_evaluator"
    assert "goal_achieved" in goal_log["output_data"]
    assert goal_log["output_data"]["goal_achieved"] == True
    assert len(goal_log["decision_log"]) > 0
    
    print(f"Goal achieved: {goal_log['output_data']['goal_achieved']}")
    print(f"Confidence: {goal_log['output_data']['confidence']:.0%}")
    print(f"Final answer length: {goal_log['output_data']['final_answer_length']}")
    print("✓ Test 8 passed")


def test_execution_log_fields():
    """Test all required fields are present in execution logs."""
    print("\n=== Test 9: ExecutionLog Field Completeness ===")
    
    required_fields = [
        "node_name",
        "execution_id",
        "correlation_id",
        "start_time",
        "end_time",
        "duration_ms",
        "execution_status",
        "input_data",
        "output_data",
        "errors",
        "warnings",
        "tool_calls",
        "decision_log",
        "context",
    ]
    
    exec_logger = ExecutionLogger("test", "corr-789")
    log = exec_logger.finalize("success")
    
    for field in required_fields:
        assert hasattr(log, field), f"Missing field: {field}"
        value = getattr(log, field)
        assert value is not None, f"Field {field} is None"
    
    log_dict = log.to_dict()
    for field in required_fields:
        assert field in log_dict, f"Missing in to_dict(): {field}"
    
    print(f"All {len(required_fields)} required fields present")
    print("✓ Test 9 passed")


def test_correlation_id_consistency():
    """Test correlation ID is consistent across nodes."""
    print("\n=== Test 10: Correlation ID Consistency ===")
    
    state = initial_state("test multi-node")
    corr_id_1 = get_correlation_id(state)
    
    # Run multiple nodes
    state = plan_node(state)
    corr_id_2 = get_correlation_id(state)
    
    state["current_plan"] = ["docker"]
    state["parallel_batches"] = [["docker"]]
    state = tool_router_node(state)
    corr_id_3 = get_correlation_id(state)
    
    # All correlation IDs should be the same
    assert corr_id_1 == corr_id_2 == corr_id_3
    
    # Verify in execution logs
    for step in state["executed_steps"]:
        if "execution_log" in step.get("data", {}):
            log = step["data"]["execution_log"]
            assert log["correlation_id"] == corr_id_1
    
    print(f"Correlation ID maintained across nodes: {corr_id_1}")
    print(f"Total execution logs: {sum(1 for s in state['executed_steps'] if 'execution_log' in s.get('data', {}))}")
    print("✓ Test 10 passed")


if __name__ == "__main__":
    try:
        test_execution_logger_basic()
        test_execution_log_to_agent_step()
        test_correlation_id_propagation()
        test_planner_node_logging()
        test_router_node_logging()
        test_executor_node_logging()
        test_verifier_node_logging()
        test_goal_evaluator_node_logging()
        test_execution_log_fields()
        test_correlation_id_consistency()
        
        print("\n" + "="*50)
        print("✓ ALL TESTS PASSED")
        print("="*50)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise
