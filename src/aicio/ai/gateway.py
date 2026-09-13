"""Provider abstraction for the language model.

Three implementations behind one interface: Anthropic, OpenAI, and an offline
gateway that answers from the facts alone with no network at all.

The offline one is not a stub. It is what CI, the eval suite, the demo and any
deployment without an API key actually run, and it is required to produce a
correct, grounded, useful answer for the common questions. Building it forced
the question "what does the model add that the engine cannot" to be answered
honestly: the model adds fluency, synthesis and conversation, not facts.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

#: The current Claude family. Opus is the default because this is a reasoning
#: task over a large grounded context where an error is expensive.
ANTHROPIC_DEFAULT_MODEL = "claude-opus-5"
OPENAI_DEFAULT_MODEL = "gpt-4.1"

HTTP_TIMEOUT = float(os.environ.get("AICIO_LLM_TIMEOUT", "60"))


class GatewayError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "model": self.model, "provider": self.provider,
            "stop_reason": self.stop_reason,
            "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in self.tool_calls],
            "usage": {"input": self.input_tokens, "output": self.output_tokens},
        }


class LLMGateway(ABC):
    name: str = "gateway"
    model: str = ""

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] = (),
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    def health(self) -> dict[str, Any]:
        return {"gateway": self.name, "model": self.model, "status": "unknown"}


def _post(url: str, payload: dict, headers: dict[str, str]) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", **headers,
    })
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise GatewayError(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GatewayError(f"{url} unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GatewayError(f"{url} returned unparseable JSON") from exc


class AnthropicGateway(LLMGateway):
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"
    VERSION = "2023-06-01"

    def __init__(self, api_key: str | None = None, *, model: str = ANTHROPIC_DEFAULT_MODEL) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise GatewayError("ANTHROPIC_API_KEY is not set")

    def complete(
        self, *, system: str, messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] = (), max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": list(messages),
        }
        if tools:
            payload["tools"] = [
                {"name": t["name"], "description": t["description"],
                 "input_schema": t["parameters"]}
                for t in tools
            ]
        data = _post(self.URL, payload, {
            "x-api-key": self.api_key, "anthropic-version": self.VERSION,
        })
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(block.get("id", ""), block.get("name", ""),
                                      block.get("input", {}) or {}))
        usage = data.get("usage", {})
        return LLMResponse(
            text="".join(text_parts).strip(), tool_calls=calls, model=data.get("model", self.model),
            provider=self.name, stop_reason=data.get("stop_reason", ""),
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
        )

    def health(self) -> dict[str, Any]:
        return {"gateway": self.name, "model": self.model, "status": "configured"}


class OpenAIGateway(LLMGateway):
    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str | None = None, *, model: str = OPENAI_DEFAULT_MODEL) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise GatewayError("OPENAI_API_KEY is not set")

    def complete(
        self, *, system: str, messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] = (), max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model, "max_tokens": max_tokens, "temperature": temperature,
            "messages": [{"role": "system", "content": system}] + _to_openai(messages),
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        data = _post(self.URL, payload, {"Authorization": f"Bearer {self.api_key}"})
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        calls = [
            ToolCall(c.get("id", ""), c["function"]["name"],
                     json.loads(c["function"].get("arguments") or "{}"))
            for c in message.get("tool_calls", []) or []
        ]
        usage = data.get("usage", {})
        return LLMResponse(
            text=(message.get("content") or "").strip(), tool_calls=calls,
            model=data.get("model", self.model), provider=self.name,
            stop_reason=choice.get("finish_reason", ""),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    def health(self) -> dict[str, Any]:
        return {"gateway": self.name, "model": self.model, "status": "configured"}


def _to_openai(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten Anthropic-shaped content blocks into OpenAI's message format."""
    out: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            out.append({"role": message["role"], "content": content})
            continue
        text_parts = []
        for block in content or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_result":
                text_parts.append(
                    f"[tool result] {block.get('content')}"
                )
        out.append({"role": message["role"], "content": "\n".join(text_parts)})
    return out


class OfflineGateway(LLMGateway):
    """Answers from the facts, with no model behind it.

    It parses the question for intent, calls the same tools a model would, and
    renders the result. The prose is plainer than a model's -- that is the
    whole difference -- but the numbers are identical, because both read the
    same engine output.

    This is what makes "the LLM is not the source of truth" a testable claim
    rather than a slogan: the eval suite runs against this gateway, so a
    regression in grounding is a code bug, not a prompt regression.
    """

    name = "offline"
    model = "aicio-offline/1"

    def __init__(self, responder: Callable[[str, Sequence[dict]], str] | None = None) -> None:
        self.responder = responder

    def complete(
        self, *, system: str, messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] = (), max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> LLMResponse:
        question = _last_user_text(messages)
        if self.responder is not None:
            return LLMResponse(self.responder(question, list(messages)), model=self.model,
                               provider=self.name, stop_reason="end_turn")
        # The banker fills this in; reaching here means it was used directly.
        return LLMResponse(
            "No language model is configured, so I can only show you the engine's own "
            "figures. Open the portfolio or action views for the numbers behind any "
            "recommendation.",
            model=self.model, provider=self.name, stop_reason="end_turn",
        )

    def health(self) -> dict[str, Any]:
        return {"gateway": self.name, "model": self.model, "status": "ok", "network": False}


def _last_user_text(messages: Sequence[dict[str, Any]]) -> str:
    for message in reversed(list(messages)):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        for block in content or []:
            if block.get("type") == "text":
                return block.get("text", "")
    return ""


def build_gateway(environ: dict[str, str] | None = None) -> LLMGateway:
    """Pick a gateway from the environment, preferring the most capable.

    Falls back to offline rather than raising. A missing API key should degrade
    the conversation, never take down the dashboard -- the engine is what the
    product is, and it does not need a model to work.
    """
    environ = environ if environ is not None else dict(os.environ)
    preference = environ.get("AICIO_LLM_PROVIDER", "").lower()
    try:
        if preference == "openai" or (not preference and environ.get("OPENAI_API_KEY")
                                      and not environ.get("ANTHROPIC_API_KEY")):
            return OpenAIGateway(environ.get("OPENAI_API_KEY"),
                                 model=environ.get("AICIO_LLM_MODEL", OPENAI_DEFAULT_MODEL))
        if preference in {"", "anthropic"} and environ.get("ANTHROPIC_API_KEY"):
            return AnthropicGateway(environ.get("ANTHROPIC_API_KEY"),
                                    model=environ.get("AICIO_LLM_MODEL", ANTHROPIC_DEFAULT_MODEL))
    except GatewayError:
        pass
    return OfflineGateway()
