"""Orchestrates prompt construction, LLM invocation, and response parsing for PR reviews."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .diff_utils import FileDiff, build_prompt_diff, parse_diff
from .github_client import InlineComment
from .llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)

VALID_VERDICTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}

STRICTNESS_GUIDANCE = {
    "lenient": (
        "Be lenient: only flag clear bugs, security vulnerabilities, or serious problems. "
        "Do not nitpick style or minor conventions."
    ),
    "standard": (
        "Use balanced judgment: flag bugs, security concerns, notable code-quality issues, "
        "and significant style problems, but avoid excessive nitpicking."
    ),
    "strict": (
        "Be strict and thorough: flag bugs, security concerns, code-quality issues, style "
        "inconsistencies, missing tests, and missing documentation."
    ),
}

SYSTEM_PROMPT_TEMPLATE = """You are an expert, meticulous software engineer performing an automated code review \
of a GitHub pull request diff. {strictness_guidance}

Review the unified diff provided by the user for:
- Bugs and logic errors
- Security vulnerabilities (injection, secrets, unsafe deserialization, etc.)
- Code quality and maintainability issues
- Style and convention problems

Respond with ONLY a single JSON object (no markdown fences, no extra prose) with this exact shape:
{{
  "verdict": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
  "summary": "one or two sentence overall summary",
  "findings": [
    {{
      "file": "path/to/file",
      "line": 123,
      "severity": "high" | "medium" | "low",
      "comment": "description of the issue and suggested fix"
    }}
  ]
}}

Use "line" as the line number in the NEW version of the file (as shown after '+' in the diff). \
If a finding does not correspond to a specific line, omit "file"/"line" for that finding. \
If there are no issues, return an empty "findings" list and an APPROVE verdict."""


@dataclass
class Finding:
    comment: str
    file: Optional[str] = None
    line: Optional[int] = None
    severity: str = "medium"


@dataclass
class ReviewResult:
    verdict: str
    summary: str
    findings: List[Finding] = field(default_factory=list)
    raw_response: str = ""

    def to_markdown(self) -> str:
        verdict_labels = {
            "APPROVE": "✅ Approve",
            "REQUEST_CHANGES": "❌ Request changes",
            "COMMENT": "💬 Comment",
        }
        lines = [
            "## 🤖 Automated PR Review",
            "",
            f"**Verdict:** {verdict_labels.get(self.verdict, self.verdict)}",
            "",
            self.summary or "_No summary provided._",
        ]

        if self.findings:
            lines.append("")
            lines.append("### Findings")
            for finding in self.findings:
                location = ""
                if finding.file:
                    location = f"`{finding.file}`"
                    if finding.line:
                        location += f" (line {finding.line})"
                    location += ": "
                severity_emoji = {"high": "🔴", "medium": "🟠", "low": "⚪"}.get(finding.severity, "🟠")
                lines.append(f"- {severity_emoji} {location}{finding.comment}")
        else:
            lines.append("")
            lines.append("_No issues found._")

        lines.append("")
        lines.append("<sub>Generated automatically by pr-review-agent. Please verify suggestions before relying on them.</sub>")
        return "\n".join(lines)


def build_user_prompt(diff_files: List[FileDiff], max_files: int, max_file_chars: int, max_total_chars: int, pr_title: str = "", pr_body: str = "") -> str:
    diff_text = build_prompt_diff(diff_files, max_files=max_files, max_file_chars=max_file_chars, max_total_chars=max_total_chars)
    header = ""
    if pr_title:
        header += f"PR Title: {pr_title}\n"
    if pr_body:
        header += f"PR Description: {pr_body}\n"
    if header:
        header += "\n"
    return f"{header}Review the following diff:\n\n{diff_text}"


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from a possibly noisy LLM response."""
    text = text.strip()
    # Strip markdown code fences if present.
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to locating the outermost braces.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    return None


def parse_llm_response(raw_response: str) -> ReviewResult:
    """Parse the LLM's JSON response into a ReviewResult, falling back to a COMMENT verdict."""
    data = _extract_json(raw_response)

    if not data:
        logger.warning("Could not parse LLM response as JSON; falling back to raw text summary")
        return ReviewResult(verdict="COMMENT", summary=raw_response.strip()[:2000], findings=[], raw_response=raw_response)

    verdict = str(data.get("verdict", "COMMENT")).upper()
    if verdict not in VALID_VERDICTS:
        verdict = "COMMENT"

    summary = str(data.get("summary", "")).strip()

    findings: List[Finding] = []
    for item in data.get("findings", []) or []:
        if not isinstance(item, dict):
            continue
        comment = str(item.get("comment", "")).strip()
        if not comment:
            continue
        line = item.get("line")
        try:
            line = int(line) if line is not None else None
        except (TypeError, ValueError):
            line = None
        severity = str(item.get("severity", "medium")).lower()
        if severity not in {"high", "medium", "low"}:
            severity = "medium"
        findings.append(Finding(comment=comment, file=item.get("file"), line=line, severity=severity))

    return ReviewResult(verdict=verdict, summary=summary, findings=findings, raw_response=raw_response)


def review_diff(
    llm_client: LLMClient,
    diff_text: str,
    strictness: str = "standard",
    max_files: int = 60,
    max_file_chars: int = 6_000,
    max_total_chars: int = 60_000,
    pr_title: str = "",
    pr_body: str = "",
) -> ReviewResult:
    """Parse the diff, build a prompt, call the LLM, and parse its response."""
    diff_files = parse_diff(diff_text)
    non_binary = [f for f in diff_files if not f.is_binary]

    if not diff_files:
        return ReviewResult(verdict="APPROVE", summary="No changes detected in the diff.", findings=[])

    if not non_binary:
        return ReviewResult(verdict="APPROVE", summary="Only binary files changed; nothing to review.", findings=[])

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        strictness_guidance=STRICTNESS_GUIDANCE.get(strictness, STRICTNESS_GUIDANCE["standard"])
    )
    user_prompt = build_user_prompt(
        diff_files, max_files=max_files, max_file_chars=max_file_chars, max_total_chars=max_total_chars,
        pr_title=pr_title, pr_body=pr_body,
    )

    try:
        raw_response = llm_client.chat(system_prompt, user_prompt)
    except LLMError:
        raise

    return parse_llm_response(raw_response)


def findings_to_inline_comments(findings: List[Finding], diff_files: List[FileDiff]) -> List[InlineComment]:
    """Convert findings with file/line info into inline comments, keeping only lines actually in the diff."""
    valid_lines = {}
    for file_diff in diff_files:
        valid_lines[file_diff.path] = set(file_diff.added_line_numbers())

    comments: List[InlineComment] = []
    for finding in findings:
        if not finding.file or not finding.line:
            continue
        if finding.line not in valid_lines.get(finding.file, set()):
            continue
        comments.append(InlineComment(path=finding.file, line=finding.line, body=f"**{finding.severity.upper()}**: {finding.comment}"))
    return comments
