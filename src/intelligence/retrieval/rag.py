from __future__ import annotations

import time
from typing import Any

from src.intelligence.providers.base import Message, ModelProvider
from src.intelligence.retrieval.base import RetrievalResult
from src.intelligence.retrieval.collector import KnowledgeCollector

SYSTEM_PROMPT_TEMPLATE = """You are an AI operations assistant for AegisNex infrastructure monitoring.
Your role is to analyze operational data and provide accurate, evidence-based answers.

## Context from operational knowledge sources:
{context}

## Instructions:
- Base your answer ONLY on the provided context and tool results.
- If the context does not contain enough information, say so.
- Cite the source of each piece of evidence.
- Be specific and precise about numbers, statuses, and timestamps.
- If the user asks about sensitive/destructive actions, flag them for approval."""


class RAGEngine:
    def __init__(
        self,
        provider: ModelProvider | None = None,
        repo: Any = None,
        runbooks_dir: str | None = None,
    ) -> None:
        self._provider = provider
        self._collector = KnowledgeCollector(repo=repo, runbooks_dir=runbooks_dir)

    def set_provider(self, provider: ModelProvider) -> None:
        self._provider = provider

    def retrieve(self, query: str, limit: int = 5) -> RetrievalResult:
        start = time.time()
        docs = self._collector.collect_all(query, limit=limit)
        elapsed = (time.time() - start) * 1000
        return RetrievalResult(
            documents=docs,
            query=query,
            total_found=len(docs),
            execution_ms=elapsed,
            strategy="knowledge_collector",
        )

    def retrieve_by_type(self, query: str, source_type: str, limit: int = 5) -> RetrievalResult:
        start = time.time()
        type_map: dict[str, Any] = {
            "incident": self._collector.collect_incidents,
            "audit": self._collector.collect_audit_logs,
            "report": self._collector.collect_reports,
            "monitoring": self._collector.collect_monitoring_history,
            "runbook": self._collector.collect_runbooks,
        }
        collector_fn = type_map.get(source_type, self._collector.collect_all)
        docs = collector_fn(query, limit=limit)
        elapsed = (time.time() - start) * 1000
        return RetrievalResult(
            documents=docs,
            query=query,
            total_found=len(docs),
            execution_ms=elapsed,
            strategy=f"knowledge_collector:{source_type}",
        )

    def generate_with_context(
        self,
        query: str,
        context: str | None = None,
        tool_results: dict[str, Any] | None = None,
    ) -> str:
        if self._provider is None:
            return self._fallback_answer(query, context, tool_results)

        if context is None:
            retrieval = self.retrieve(query)
            context = retrieval.context_text

        tool_text = ""
        if tool_results:
            parts = []
            for name, result in tool_results.items():
                status = result.get("status", "?")
                summary = str(result)[:300]
                parts.append(f"Tool '{name}' (status: {status}): {summary}")
            tool_text = "\n".join(parts)

        full_context = (
            f"## Retrieved Knowledge\n{context}\n\n## Tool Results\n{tool_text}"
            if tool_text
            else f"## Retrieved Knowledge\n{context}"
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=full_context)

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=query),
        ]

        try:
            response = self._provider.chat(messages)
            return response.content
        except Exception:
            return self._fallback_answer(query, context, tool_results)

    def _fallback_answer(
        self, query: str, context: str | None = None, tool_results: dict[str, Any] | None = None
    ) -> str:
        parts = ["Based on available operational data:"]
        if tool_results:
            for name, result in tool_results.items():
                status = result.get("status", "?")
                data = {k: v for k, v in result.items() if k not in ("status", "tool", "timestamp")}
                parts.append(f"\n**{name}** ({status}): {str(data)[:400]}")
        if context:
            parts.append(f"\n**Context:** {context[:500]}")
        parts.append(
            "\n*Note: This is a rule-based response. Configure an AI provider (AEGIS_AI_PROVIDER) for LLM-generated answers.*"
        )
        return "\n".join(parts)
