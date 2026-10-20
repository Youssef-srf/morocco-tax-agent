"""Deterministic stand-ins for Gemini, so the tests run offline and for free."""

import hashlib
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class BagOfWords:
    """Stand-in for an embedding model: hashed word counts."""

    dim = 768

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in re.findall(r"\w{4,}", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1
        return v

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


class ScriptedChatModel(BaseChatModel):
    """Returns the given AI messages in order, and records what it was sent."""

    script: list[AIMessage]
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.script[len(self.calls) - 1])])
