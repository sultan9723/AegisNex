from __future__ import annotations

from typing import Any, Dict, List, Optional

import google.generativeai as genai

from src.intelligence.providers.base import (
    Message,
    ModelProvider,
    ProviderConfig,
    ToolCall,
)


class GeminiProvider(ModelProvider):
    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        genai.configure(api_key=self.config.api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _to_gemini_history(self, messages: List[Message]) -> List[Dict[str, Any]]:
        history = []
        for m in messages:
            if m.role == "system":
                continue
            role = "model" if m.role == "assistant" else "user"
            history.append({"role": role, "parts": [m.content]})
        return history

    def chat(self, messages: List[Message], **kwargs: Any) -> Message:
        model_name = kwargs.get("model", self.config.model)
        system_instruction = None
        for m in messages:
            if m.role == "system":
                system_instruction = m.content
        history = self._to_gemini_history(messages)
        model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)
        chat = model.start_chat(history=history[:-1] if history else [])
        resp = chat.send_message(history[-1]["parts"][0] if history else "")
        return Message(role="assistant", content=resp.text)

    def chat_with_tools(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Message:
        model_name = kwargs.get("model", self.config.model)
        system_instruction = None
        for m in messages:
            if m.role == "system":
                system_instruction = m.content
        gemini_tools = []
        for t in tools:
            fn = t.get("function", t)
            gemini_tools.append({"function_declarations": [{"name": fn.get("name", ""), "description": fn.get("description", ""), "parameters": fn.get("parameters", {"type": "object", "properties": {}})}]})
        model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction, tools=gemini_tools)
        history = self._to_gemini_history(messages)
        chat = model.start_chat(history=history[:-1] if history else [])
        resp = chat.send_message(history[-1]["parts"][0] if history else "")
        text = resp.text if hasattr(resp, "text") else ""
        tool_calls = []
        if hasattr(resp, "candidates") and resp.candidates:
            for part in resp.candidates[0].content.parts:
                if hasattr(part, "function_call"):
                    tc = part.function_call
                    tool_calls.append(ToolCall(name=tc.name, args=dict(tc.args), id=""))
        return Message(role="assistant", content=text, tool_calls=tool_calls)

    def embed(self, text: str, **kwargs: Any) -> List[float]:
        model_name = kwargs.get("model", "text-embedding-004")
        result = genai.embed_content(model=model_name, content=text)
        return result.get("embedding", [])
