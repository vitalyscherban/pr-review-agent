import json

import pytest

from pr_review_agent.config import Config
from pr_review_agent.github_client import GitHubAPIError
from pr_review_agent.llm_client import LLMError
from pr_review_agent import main as main_module
from tests.fixtures import SAMPLE_DIFF


class FakeGitHubClient:
    def __init__(self, pr=None, diff=SAMPLE_DIFF, fail_get_pr=None, fail_post_review=None):
        self.pr = pr or {"title": "t", "body": "b", "head": {"sha": "sha1"}}
        self.diff = diff
        self.fail_get_pr = fail_get_pr
        self.fail_post_review = fail_post_review
        self.posted_reviews = []
        self.posted_comments = []

    def get_pr(self, pr_number):
        if self.fail_get_pr:
            raise self.fail_get_pr
        return self.pr

    def get_pr_diff(self, pr_number):
        return self.diff

    def post_review(self, pr_number, sha, body, event, comments=None):
        if self.fail_post_review:
            raise self.fail_post_review
        self.posted_reviews.append((pr_number, sha, body, event, comments))
        return {"id": 1}

    def post_issue_comment(self, pr_number, body):
        self.posted_comments.append((pr_number, body))
        return {"id": 2}


class FakeLLMClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def chat(self, system_prompt, user_prompt, **kwargs):
        if self.error:
            raise self.error
        return self.response


def make_config(**overrides):
    base = dict(
        github_token="tok",
        repository="octo/demo",
        pr_number=42,
        event_name="pull_request",
        model="gpt-4o-mini",
        endpoint="https://example.test",
        strictness="standard",
        max_diff_chars=60_000,
        max_files=60,
        post_inline_comments=True,
        dry_run=False,
    )
    base.update(overrides)
    return Config(**base)


def test_run_missing_token_returns_error(monkeypatch):
    config = make_config(github_token="")
    assert main_module.run(config) == 1


def test_run_missing_repo_returns_error(monkeypatch):
    config = make_config(repository="")
    assert main_module.run(config) == 1


def test_run_success_posts_review(monkeypatch):
    fake_github = FakeGitHubClient()
    fake_llm = FakeLLMClient(response=json.dumps({"verdict": "APPROVE", "summary": "ok", "findings": []}))

    monkeypatch.setattr(main_module, "GitHubClient", lambda **kwargs: fake_github)
    monkeypatch.setattr(main_module, "LLMClient", lambda **kwargs: fake_llm)

    config = make_config()
    exit_code = main_module.run(config)

    assert exit_code == 0
    assert len(fake_github.posted_reviews) == 1
    pr_number, sha, body, event, comments = fake_github.posted_reviews[0]
    assert event == "APPROVE"
    assert "Automated PR Review" in body


def test_run_llm_failure_posts_failure_comment_and_returns_1(monkeypatch):
    fake_github = FakeGitHubClient()
    fake_llm = FakeLLMClient(error=LLMError("service unavailable"))

    monkeypatch.setattr(main_module, "GitHubClient", lambda **kwargs: fake_github)
    monkeypatch.setattr(main_module, "LLMClient", lambda **kwargs: fake_llm)

    config = make_config()
    exit_code = main_module.run(config)

    assert exit_code == 1
    assert len(fake_github.posted_comments) == 1
    assert "error calling the LLM service" in fake_github.posted_comments[0][1]


def test_run_dry_run_does_not_post(monkeypatch, capsys):
    fake_github = FakeGitHubClient()
    fake_llm = FakeLLMClient(response=json.dumps({"verdict": "COMMENT", "summary": "ok", "findings": []}))

    monkeypatch.setattr(main_module, "GitHubClient", lambda **kwargs: fake_github)
    monkeypatch.setattr(main_module, "LLMClient", lambda **kwargs: fake_llm)

    config = make_config(dry_run=True)
    exit_code = main_module.run(config)

    assert exit_code == 0
    assert len(fake_github.posted_reviews) == 0
    assert len(fake_github.posted_comments) == 0
    captured = capsys.readouterr()
    assert "Automated PR Review" in captured.out


def test_run_falls_back_to_issue_comment_when_review_post_fails(monkeypatch):
    fake_github = FakeGitHubClient(fail_post_review=GitHubAPIError("cannot review own PR"))
    fake_llm = FakeLLMClient(response=json.dumps({"verdict": "COMMENT", "summary": "ok", "findings": []}))

    monkeypatch.setattr(main_module, "GitHubClient", lambda **kwargs: fake_github)
    monkeypatch.setattr(main_module, "LLMClient", lambda **kwargs: fake_llm)

    config = make_config()
    exit_code = main_module.run(config)

    assert exit_code == 0
    assert len(fake_github.posted_comments) == 1


def test_run_get_pr_failure_returns_1(monkeypatch):
    fake_github = FakeGitHubClient(fail_get_pr=GitHubAPIError("not found"))
    fake_llm = FakeLLMClient()

    monkeypatch.setattr(main_module, "GitHubClient", lambda **kwargs: fake_github)
    monkeypatch.setattr(main_module, "LLMClient", lambda **kwargs: fake_llm)

    config = make_config()
    assert main_module.run(config) == 1
