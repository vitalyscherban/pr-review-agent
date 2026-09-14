import pytest
import responses

from pr_review_agent.github_client import GitHubAPIError, GitHubClient, InlineComment

REPO = "octo/demo"
TOKEN = "fake-token"


@pytest.fixture
def client():
    return GitHubClient(token=TOKEN, repository=REPO)


@responses.activate
def test_get_pr_diff_returns_raw_diff(client):
    responses.add(
        responses.GET,
        f"https://api.github.com/repos/{REPO}/pulls/42",
        body="diff --git a/x b/x\n",
        status=200,
        content_type="application/vnd.github.v3.diff",
    )
    diff = client.get_pr_diff(42)
    assert diff == "diff --git a/x b/x\n"


@responses.activate
def test_get_pr_returns_json(client):
    responses.add(
        responses.GET,
        f"https://api.github.com/repos/{REPO}/pulls/42",
        json={"title": "Add feature", "head": {"sha": "abc123"}},
        status=200,
    )
    pr = client.get_pr(42)
    assert pr["title"] == "Add feature"
    assert pr["head"]["sha"] == "abc123"


@responses.activate
def test_post_issue_comment(client):
    responses.add(
        responses.POST,
        f"https://api.github.com/repos/{REPO}/issues/42/comments",
        json={"id": 1, "body": "hello"},
        status=201,
    )
    result = client.post_issue_comment(42, "hello")
    assert result["id"] == 1


@responses.activate
def test_post_review_includes_inline_comments(client):
    responses.add(
        responses.POST,
        f"https://api.github.com/repos/{REPO}/pulls/42/reviews",
        json={"id": 99},
        status=200,
    )
    comments = [InlineComment(path="a.py", line=3, body="issue")]
    result = client.post_review(42, "sha123", "body text", "COMMENT", comments=comments)
    assert result["id"] == 99
    sent_payload = responses.calls[0].request.body
    assert b"a.py" in sent_payload
    assert b"sha123" in sent_payload


@responses.activate
def test_request_raises_on_error_status(client):
    responses.add(
        responses.GET,
        f"https://api.github.com/repos/{REPO}/pulls/42",
        json={"message": "Not Found"},
        status=404,
    )
    with pytest.raises(GitHubAPIError):
        client.get_pr(42)


@responses.activate
def test_request_raises_on_rate_limit(client):
    responses.add(
        responses.GET,
        f"https://api.github.com/repos/{REPO}/pulls/42",
        json={"message": "API rate limit exceeded"},
        status=403,
    )
    with pytest.raises(GitHubAPIError, match="rate limit"):
        client.get_pr(42)
