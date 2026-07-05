"""Test for Phase C1: Tool Router Node"""

from src.intelligence.tool_router import ToolRouter, ToolRouterConfig
from src.intelligence.nodes import tool_router_node
from src.intelligence.state import initial_state
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_tool_router_basic():
    """Test basic tool routing functionality."""
    print("\n=== Test 1: Basic Tool Routing ===")
    
    router_config = ToolRouterConfig(logger=logger, strict_mode=False)
    router = ToolRouter(config=router_config)
    
    plan = ["metrics", "docker", "incident", "health"]
    result = router.route_plan(plan)
    
    print(f"Input plan: {plan}")
    print(f"Routing result: {result}")
    print(f"Routed tools: {result['routed_tools']}")
    print(f"Invalid tasks: {result['invalid_tasks']}")
    assert result['success'] == True
    assert len(result['routed_tools']) == 4
    print("✓ Test 1 passed")


def test_tool_router_with_invalid_tasks():
    """Test router handling of invalid tasks."""
    print("\n=== Test 2: Invalid Tasks ===")
    
    router_config = ToolRouterConfig(logger=logger, strict_mode=False)
    router = ToolRouter(config=router_config)
    
    plan = ["metrics", "invalid_tool", "docker", "nonexistent"]
    result = router.route_plan(plan)
    
    print(f"Input plan: {plan}")
    print(f"Routing result: {result}")
    print(f"Routed tools: {result['routed_tools']}")
    print(f"Invalid tasks: {result['invalid_tasks']}")
    assert result['routed_tools'] == ["metrics", "docker"]
    assert set(result['invalid_tasks']) == {"invalid_tool", "nonexistent"}
    print("✓ Test 2 passed")


def test_tool_router_metadata():
    """Test tool metadata retrieval."""
    print("\n=== Test 3: Tool Metadata Retrieval ===")
    
    router = ToolRouter()
    
    metrics_meta = router.get_tool_metadata("metrics")
    print(f"Metrics metadata: {metrics_meta}")
    assert metrics_meta is not None
    assert metrics_meta['name'] == 'metrics'
    assert metrics_meta['category'] == 'monitoring'
    assert metrics_meta['risk_level'] == 'none'
    print("✓ Test 3 passed")


def test_tool_router_node():
    """Test the tool router node in the LangGraph state."""
    print("\n=== Test 4: Tool Router Node in LangGraph ===")
    
    state = initial_state("check system metrics and docker containers")
    
    # Simulate planner output
    state['objective'] = 'Investigate system metrics'
    state['current_plan'] = ['metrics', 'docker', 'health', 'invalid_tool']
    state['parallel_batches'] = [['metrics', 'health'], ['docker'], ['invalid_tool']]
    
    print(f"Input state plan: {state['current_plan']}")
    print(f"Input parallel batches: {state['parallel_batches']}")
    
    # Run the router node
    updated_state = tool_router_node(state)
    
    print(f"Updated plan: {updated_state['current_plan']}")
    print(f"Updated parallel batches: {updated_state['parallel_batches']}")
    print(f"Router results: {updated_state['tool_router_results']}")
    print(f"Executed steps: {[s for s in updated_state['executed_steps'] if s['node'] == 'tool_router']}")
    
    # Verify router filtered out invalid tool
    assert 'invalid_tool' not in updated_state['current_plan']
    assert updated_state['current_plan'] == ['metrics', 'docker', 'health']
    
    # Verify router updated executed_steps
    router_steps = [s for s in updated_state['executed_steps'] if s['node'] == 'tool_router']
    assert len(router_steps) > 0
    
    # Verify tool_router_results are populated
    assert 'timestamp' in updated_state['tool_router_results']
    assert 'routed_tools' in updated_state['tool_router_results']
    assert 'decisions' in updated_state['tool_router_results']
    
    print("✓ Test 4 passed")


def test_tool_router_logging():
    """Test that all routing decisions are logged."""
    print("\n=== Test 5: Routing Decision Logging ===")
    
    router_config = ToolRouterConfig(logger=logger, strict_mode=False)
    router = ToolRouter(config=router_config)
    
    plan = ["metrics", "docker", "incident"]
    result = router.route_plan(plan)
    
    log = router.get_routing_log()
    print(f"Routing log: {log}")
    
    assert len(log) == 3
    for decision in log:
        print(f"  - {decision['tool_name']}: found={decision['found']}")
        assert decision['found'] == True
    
    print("✓ Test 5 passed")


if __name__ == "__main__":
    try:
        test_tool_router_basic()
        test_tool_router_with_invalid_tasks()
        test_tool_router_metadata()
        test_tool_router_node()
        test_tool_router_logging()
        print("\n" + "="*50)
        print("✓ ALL TESTS PASSED")
        print("="*50)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        raise
