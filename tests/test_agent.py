import logging

import pytest

from src.agent import AgentX


class RunnableCommand:
    def run(self, payload):
        return {"ran": payload}


class StatsCommand:
    def get_stats(self, payload):
        return {"stats": payload}


def test_agent_executes_callable_run_and_get_stats() -> None:
    agent = AgentX(logger=logging.getLogger("tests.agent"))
    agent.register_command("callable", lambda payload: {"called": payload})
    agent.register_command("runner", RunnableCommand())
    agent.register_command("stats", StatsCommand())

    assert agent.execute_task("callable", {"x": 1}) == {"called": {"x": 1}}
    assert agent.execute_task("stats", {"x": 2}) == {"stats": {"x": 2}}
    assert agent.execute_task("runner", {"x": 3}) == {"ran": {"x": 3}}


def test_agent_rejects_invalid_and_unknown_commands() -> None:
    agent = AgentX(logger=logging.getLogger("tests.agent"))

    with pytest.raises(ValueError):
        agent.register_command("", object())
    with pytest.raises(KeyError):
        agent.execute_task("missing")


def test_agent_raises_when_command_has_no_interface() -> None:
    agent = AgentX(logger=logging.getLogger("tests.agent"))
    agent.register_command("bad", object())

    with pytest.raises(AttributeError):
        agent.execute_task("bad")


def test_agent_registers_command_by_path() -> None:
    agent = AgentX(logger=logging.getLogger("tests.agent"))

    instance = agent.register_command_by_path(
        "agent", "src.agent", "AgentX", logger=logging.getLogger("tests.child")
    )

    assert isinstance(instance, AgentX)
    assert agent.commands["agent"] is instance
