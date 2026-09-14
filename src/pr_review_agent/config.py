"""Configuration for the PR review agent, sourced from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"

VALID_STRICTNESS = {"lenient", "standard", "strict"}

# Rough character budget kept well under typical model context windows so we
# leave room for the system prompt, instructions, and the model's response.
MAX_DIFF_CHARS = 60_000
MAX_FILES_IN_PROMPT = 60
MAX_FILE_DIFF_CHARS = 6_000

BINARY_MARKERS = ("GIT binary patch", "Binary files")


@dataclass
class Config:
    """Runtime configuration for the agent, populated from environment variables."""

    github_token: str = ""
    repository: str = ""
    pr_number: int = 0
    event_name: str = ""
    model: str = DEFAULT_MODEL
    endpoint: str = DEFAULT_ENDPOINT
    strictness: str = "standard"
    max_diff_chars: int = MAX_DIFF_CHARS
    max_files: int = MAX_FILES_IN_PROMPT
    post_inline_comments: bool = True
    dry_run: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        env = env if env is not None else os.environ

        strictness = env.get("REVIEW_STRICTNESS", "standard").strip().lower() or "standard"
        if strictness not in VALID_STRICTNESS:
            strictness = "standard"

        def _bool(name: str, default: bool) -> bool:
            value = env.get(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        def _int(name: str, default: int) -> int:
            value = env.get(name)
            if not value:
                return default
            try:
                return int(value)
            except ValueError:
                return default

        pr_number = 0
        raw_pr_number = env.get("PR_NUMBER")
        if raw_pr_number:
            try:
                pr_number = int(raw_pr_number)
            except ValueError:
                pr_number = 0

        return cls(
            github_token=env.get("GITHUB_TOKEN", ""),
            repository=env.get("GITHUB_REPOSITORY", ""),
            pr_number=pr_number,
            event_name=env.get("GITHUB_EVENT_NAME", ""),
            model=env.get("MODEL_NAME") or env.get("INPUT_MODEL") or DEFAULT_MODEL,
            endpoint=env.get("MODELS_ENDPOINT", DEFAULT_ENDPOINT),
            strictness=strictness,
            max_diff_chars=_int("MAX_DIFF_CHARS", MAX_DIFF_CHARS),
            max_files=_int("MAX_FILES_IN_PROMPT", MAX_FILES_IN_PROMPT),
            post_inline_comments=_bool("POST_INLINE_COMMENTS", True),
            dry_run=_bool("DRY_RUN", False),
        )
