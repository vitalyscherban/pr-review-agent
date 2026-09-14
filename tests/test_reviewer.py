import json

import pytest

from pr_review_agent.diff_utils import parse_diff
from pr_review_agent.llm_client import LLMError
from pr_review_agent.reviewer import (
    Finding,
    build_user_prompt,
    findings_to_inline_comments,
    parse_llm_response,
    review_diff,
)
from tests.fixtures import SAMPLE_DIFF


class FakeLLMClient:
    def __init__(self, response=None, raise_error=None):
        self.response = response
        self.raise_error = raise_error
        self.last_call = None

    def chat(self, system_prompt, user_prompt, **kwargs):
        self.last_call = (system_prompt, user_prompt)
        if self.raise_error:
            raise self.raise_error
        return self.response


def test_build_user_prompt_includes_title_and_diff():
    files = parse_diff(SAMPLE_DIFF)
    prompt = build_user_prompt(files, max_files=10, max_file_chars=10_000, max_total_chars=100_000, pr_title="Fix bug", pr_body="Fixes #1")
    assert "PR Title: Fix bug" in prompt
    assert "PR Description: Fixes #1" in prompt
    assert "diff --git" in prompt


def test_parse_llm_response_valid_json():
    payload = json.dumps({
        "verdict": "REQUEST_CHANGES",
        "summary": "Found a hardcoded secret.",
        "findings": [
            {"file": "src/new_file.py", "line": 1, "severity": "high", "comment": "Hardcoded password."}
        ],
    })
    result = parse_llm_response(payload)
    assert result.verdict == "REQUEST_CHANGES"
    assert result.summary == "Found a hardcoded secret."
    assert len(result.findings) == 1
    assert result.findings[0].file == "src/new_file.py"
    assert result.findings[0].severity == "high"


def test_parse_llm_response_strips_markdown_fences():
    payload = "```json\n" + json.dumps({"verdict": "APPROVE", "summary": "LGTM", "findings": []}) + "\n```"
    result = parse_llm_response(payload)
    assert result.verdict == "APPROVE"
    assert result.summary == "LGTM"


def test_parse_llm_response_invalid_json_falls_back_to_comment():
    result = parse_llm_response("This is not JSON at all.")
    assert result.verdict == "COMMENT"
    assert "not JSON" in result.summary


def test_parse_llm_response_normalizes_invalid_verdict_and_severity():
    payload = json.dumps({
        "verdict": "REJECT",
        "summary": "s",
        "findings": [{"comment": "bad severity", "severity": "critical"}],
    })
    result = parse_llm_response(payload)
    assert result.verdict == "COMMENT"
    assert result.findings[0].severity == "medium"


def test_review_diff_success_path():
    fake_response = json.dumps({"verdict": "APPROVE", "summary": "Looks fine", "findings": []})
    client = FakeLLMClient(response=fake_response)
    result = review_diff(client, SAMPLE_DIFF)
    assert result.verdict == "APPROVE"
    assert client.last_call is not None
    system_prompt, user_prompt = client.last_call
    assert "diff" in user_prompt.lower()


def test_review_diff_binary_only_diff_short_circuits():
    binary_only_diff = """diff --git a/img.png b/img.png
new file mode 100644
Binary files /dev/null and b/img.png differ
"""
    client = FakeLLMClient(response="should not be called")
    result = review_diff(client, binary_only_diff)
    assert result.verdict == "APPROVE"
    assert client.last_call is None


def test_review_diff_empty_diff_short_circuits():
    client = FakeLLMClient(response="should not be called")
    result = review_diff(client, "")
    assert result.verdict == "APPROVE"
    assert client.last_call is None


def test_review_diff_propagates_llm_error():
    client = FakeLLMClient(raise_error=LLMError("boom"))
    with pytest.raises(LLMError):
        review_diff(client, SAMPLE_DIFF)


def test_review_result_to_markdown_includes_findings():
    fake_response = json.dumps({
        "verdict": "REQUEST_CHANGES",
        "summary": "Issues found.",
        "findings": [{"file": "a.py", "line": 5, "severity": "high", "comment": "Bug here."}],
    })
    result = parse_llm_response(fake_response)
    markdown = result.to_markdown()
    assert "Request changes" in markdown
    assert "a.py" in markdown
    assert "line 5" in markdown
    assert "Bug here." in markdown


def test_findings_to_inline_comments_filters_invalid_lines():
    files = parse_diff(SAMPLE_DIFF)
    findings = [
        Finding(comment="valid", file="src/new_file.py", line=1, severity="high"),
        Finding(comment="invalid line not in diff", file="src/new_file.py", line=999, severity="low"),
        Finding(comment="no file reference", file=None, line=None, severity="medium"),
    ]
    comments = findings_to_inline_comments(findings, files)
    assert len(comments) == 1
    assert comments[0].path == "src/new_file.py"
    assert comments[0].line == 1
