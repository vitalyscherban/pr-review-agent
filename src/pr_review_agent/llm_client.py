"""Client for calling the GitHub Models inference endpoint (OpenAI-compatible chat API)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2000


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns an unusable response."""


@dataclass
class ChatMessage:
    role: str
    content: str


class LLMClient:
    """Calls the GitHub Models chat-completions endpoint with a system + user prompt."""

    def __init__(
        self,
        token: str,
        model: str,
        endpoint: str,
        session: Optional[requests.Session] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.token = token
        self.model = model
        self.endpoint = endpoint
        self.session = session or requests.Session()
        self.timeout = timeout

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """Send a chat completion request and return the assistant's text response."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"Network error calling GitHub Models endpoint: {exc}") from exc

        if response.status_code == 429:
            raise LLMError(f"GitHub Models rate limit exceeded: {response.text}")
        if response.status_code >= 400:
            raise LLMError(f"GitHub Models API error {response.status_code}: {response.text}")

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response shape from GitHub Models: {exc}; body={response.text[:500]}") from exc
