"""Test the Intelligence Engine workflow."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))

from src.intelligence.graph import run_chat, run_analyze, run_plan, reset_graph

# Test planning
result = run_plan("What happened with incidents today?")
print("=== PLAN ===")
print("Objective:", result.get("objective"))
print("Steps:", result.get("current_plan"))
print()

# Test full chat workflow
reset_graph()
result = run_chat("Check system health")
print("=== CHAT ===")
print("Goal achieved:", result.get("goal_achieved"))
print("Confidence:", result.get("confidence"))
print("Steps executed:", len(result.get("steps", [])))
for s in result.get("steps", []):
    node = s.get("node", "?")
    status = s.get("status", "?")
    detail = s.get("detail", "")[:80]
    print("  {}: {} - {}".format(node, status, detail))
print()

# Test analyze
reset_graph()
result = run_analyze("Show me the audit logs")
print("=== ANALYZE ===")
print("Goal achieved:", result.get("goal_achieved"))
print("Executed steps:", len(result.get("executed_steps", [])))
print()

# Test all request types
for req in [
    "Why is CPU high?",
    "List Docker containers",
    "Check monitoring targets",
    "Generate a weekly report",
    "What is the notification status?",
    "Analyze Incident #42",
    "Show overall health",
]:
    reset_graph()
    result = run_plan(req)
    print("{:40s} -> {}".format(req[:38], result.get("objective", "?")))
    print("  Steps: {}".format(result.get("current_plan", [])))
    print()
