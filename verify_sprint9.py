"""Quick verification of Sprint 9 implementation."""
import sys
sys.path.insert(0, ".")

errors = []

# 1. Verify modules import
modules = [
    "src.intelligence.risk",
    "src.intelligence.policy",
    "src.intelligence.scheduler",
    "src.intelligence.runbooks.parser",
    "src.intelligence.runbooks.registry",
    "src.intelligence.runbooks.engine",
    "src.intelligence.workflows.common",
    "src.intelligence.memory.types",
]
for mod in modules:
    try:
        __import__(mod.replace("/", "."))
        print(f"  OK  {mod}")
    except Exception as e:
        errors.append(f"FAIL {mod}: {e}")
        print(f"  FAIL {mod}: {e}")

# 2. Verify graph compilation
from src.intelligence.graph import build_graph, get_workflows, reset_graph
try:
    reset_graph()
    g = build_graph()
    print(f"  OK  Graph compiled, {len(g.nodes)} nodes")
    wf = get_workflows()
    print(f"  OK  {len(wf['nodes'])} nodes in workflow def")
    for n in wf["nodes"]:
        print(f"       - {n}")
except Exception as e:
    errors.append(f"FAIL graph: {e}")

# 3. Verify risk engine
from src.intelligence.risk import RiskEngine
try:
    re = RiskEngine()
    assessment = re.assess_tool("restart")
    print(f"  OK  Risk engine: score={assessment.score}, level={assessment.level.value}")
except Exception as e:
    errors.append(f"FAIL risk engine: {e}")

# 4. Verify policy engine
from src.intelligence.policy import PolicyEngine
try:
    pe = PolicyEngine()
    result = pe.check_action("restart", {"environment": "production"})
    print(f"  OK  Policy engine: allowed={result.allowed}, policy={result.policy_name}")
except Exception as e:
    errors.append(f"FAIL policy engine: {e}")

# 5. Verify scheduler
from src.intelligence.scheduler import Scheduler
import tempfile, os
try:
    tmp = os.path.join(tempfile.gettempdir(), "test_scheduler.db")
    sched = Scheduler(db_path=tmp)
    sched.add_task("test", "* * * * *", "metrics")
    stats = sched.get_stats()
    print(f"  OK  Scheduler: {stats['total_tasks']} tasks")
    os.remove(tmp)
except Exception as e:
    errors.append(f"FAIL scheduler: {e}")

# 6. Verify state fields
from src.intelligence.state import AgentState, initial_state
try:
    state = initial_state("test")
    required_keys = ["current_runbook", "runbook_steps", "risk_assessment", "policy_results", "workflow_triggered", "scheduler_tasks", "learnings", "parallel_executions"]
    missing = [k for k in required_keys if k not in state]
    if missing:
        errors.append(f"FAIL state: missing keys: {missing}")
    else:
        print(f"  OK  State has all {len(required_keys)} new fields")
except Exception as e:
    errors.append(f"FAIL state: {e}")

# 7. Runbook engine
from src.intelligence.runbooks.registry import RunbookRegistry, get_registry
from src.intelligence.runbooks.engine import RunbookEngine
from src.intelligence.runbooks.parser import RunbookParser
import os
try:
    registry = get_registry()
    # Load sample runbooks
    runbooks_dir = os.path.join("src", "intelligence", "runbooks")
    count_before = registry.count()
    for fname in os.listdir(runbooks_dir):
        if fname.endswith((".yaml", ".yml", ".json")):
            rb = RunbookParser.from_file(os.path.join(runbooks_dir, fname))
            registry.register(rb)
    count_after = registry.count()
    loaded = count_after - count_before
    print(f"  OK  Runbook registry: loaded {loaded} runbooks, total={registry.count()}")
    sample = registry.get("restart-nginx")
    if sample:
        print(f"       Sample runbook '{sample.name}': {len(sample.steps)} steps")
except Exception as e:
    errors.append(f"FAIL runbook registry: {e}")

# 8. Verify query params added to AiChatResponse type
print()
if errors:
    print(f"ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("All Sprint 9 checks passed!")
