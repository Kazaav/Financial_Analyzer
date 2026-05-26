from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AIResult:
    text: str
    provider: str
    model: str


class BaseAIProvider:
    name = "none"

    def is_configured(self) -> bool:
        return False

    def summarize(self, prompt: str) -> AIResult | None:
        return None


class NoAIProvider(BaseAIProvider):
    name = "none"


class DeepSeekProvider(BaseAIProvider):
    name = "deepseek"

    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def summarize(self, prompt: str) -> AIResult | None:
        # API hookup is intentionally deferred. The app calls this only when
        # AI_PROVIDER=deepseek and a future implementation enables it.
        if not self.is_configured():
            return None
        return None


class MiniMaxProvider(BaseAIProvider):
    name = "minimax"

    def __init__(self) -> None:
        self.api_key = os.getenv("MINIMAX_API_KEY", "")
        self.model = os.getenv("MINIMAX_MODEL", "abab6.5s-chat")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def summarize(self, prompt: str) -> AIResult | None:
        if not self.is_configured():
            return None
        return None


def get_ai_provider() -> BaseAIProvider:
    provider = os.getenv("AI_PROVIDER", "none").strip().lower()
    if provider == "deepseek":
        return DeepSeekProvider()
    if provider == "minimax":
        return MiniMaxProvider()
    return NoAIProvider()

