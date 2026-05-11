"""Deterministic task router for small specialized local models."""

from __future__ import annotations

import re
from dataclasses import dataclass


_CODE_PATTERNS = re.compile(
    r"\b(code|python|bash|shell|script|function|class|bug|debug|traceback|"
    r"compile|sql|json|yaml|regex|refactor|exception|stack trace)\b|```",
    re.IGNORECASE,
)
_UTILITY_PATTERNS = re.compile(
    r"\b(summarize|classify|rewrite|extract|bullet|title|slug|shorten|"
    r"yes/no|sentiment)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteDecision:
    """Result of routing an inference request."""

    model_key: str
    reason: str


class TaskRouter:
    """A transparent rule-based router with no model-side overhead."""

    def __init__(self, available_models: set[str]) -> None:
        self.available_models = available_models

    def route(self, prompt: str, requested_task: str | None = None) -> RouteDecision:
        """Choose a model key from task metadata and prompt hints."""

        task = (requested_task or "").strip().lower()
        if task in self.available_models:
            return RouteDecision(task, "explicit model key requested")
        if task in {"coding", "code", "programming"} and "code" in self.available_models:
            return RouteDecision("code", "explicit coding task")
        if task in {"utility", "summarize", "classify", "rewrite"} and "utility" in self.available_models:
            return RouteDecision("utility", "explicit utility task")
        if _CODE_PATTERNS.search(prompt) and "code" in self.available_models:
            return RouteDecision("code", "prompt matched code-oriented routing rule")
        if _UTILITY_PATTERNS.search(prompt) and "utility" in self.available_models:
            return RouteDecision("utility", "prompt matched utility routing rule")
        fallback = "general" if "general" in self.available_models else sorted(self.available_models)[0]
        return RouteDecision(fallback, "stable general fallback")
