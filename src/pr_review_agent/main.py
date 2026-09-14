"""Entrypoint for the PR review agent GitHub Action."""
from __future__ import annotations

import logging
import sys

from .config import Config
from .github_client import GitHubAPIError, GitHubClient
from .llm_client import LLMClient, LLMError
from .reviewer import findings_to_inline_comments, review_diff
from .diff_utils import parse_diff

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pr_review_agent")

VERDICT_TO_EVENT = {
    "APPROVE": "APPROVE",
    "REQUEST_CHANGES": "REQUEST_CHANGES",
    "COMMENT": "COMMENT",
}


def run(config: Config) -> int:
    """Run the full review flow. Returns a process exit code (0 on success)."""
    if not config.github_token:
        logger.error("GITHUB_TOKEN is not set; cannot call the GitHub API.")
        return 1
    if not config.repository or not config.pr_number:
        logger.error("GITHUB_REPOSITORY and PR_NUMBER must be set (repository=%s, pr_number=%s).", config.repository, config.pr_number)
        return 1

    github_client = GitHubClient(token=config.github_token, repository=config.repository)
    llm_client = LLMClient(token=config.github_token, model=config.model, endpoint=config.endpoint)

    try:
        pr = github_client.get_pr(config.pr_number)
        diff_text = github_client.get_pr_diff(config.pr_number)
    except GitHubAPIError as exc:
        logger.error("Failed to fetch PR data: %s", exc)
        return 1

    pr_title = pr.get("title", "")
    pr_body = pr.get("body") or ""
    head_sha = pr.get("head", {}).get("sha", "")

    try:
        result = review_diff(
            llm_client,
            diff_text,
            strictness=config.strictness,
            max_files=config.max_files,
            max_total_chars=config.max_diff_chars,
            pr_title=pr_title,
            pr_body=pr_body,
        )
    except LLMError as exc:
        logger.error("LLM review failed: %s", exc)
        if not config.dry_run:
            try:
                github_client.post_issue_comment(
                    config.pr_number,
                    "## 🤖 Automated PR Review\n\n⚠️ The automated review could not be completed due to an "
                    f"error calling the LLM service:\n\n```\n{exc}\n```\n\nPlease re-run the workflow or review manually.",
                )
            except GitHubAPIError as post_exc:
                logger.error("Additionally failed to post the failure comment: %s", post_exc)
        return 1

    body = result.to_markdown()
    logger.info("Review verdict: %s (%d findings)", result.verdict, len(result.findings))

    if config.dry_run:
        print(body)
        return 0

    inline_comments = []
    if config.post_inline_comments:
        diff_files = parse_diff(diff_text)
        inline_comments = findings_to_inline_comments(result.findings, diff_files)

    event = VERDICT_TO_EVENT.get(result.verdict, "COMMENT")

    try:
        if head_sha:
            github_client.post_review(config.pr_number, head_sha, body, event, comments=inline_comments)
        else:
            github_client.post_issue_comment(config.pr_number, body)
    except GitHubAPIError as exc:
        logger.warning("Failed to post full review (%s); falling back to a plain issue comment.", exc)
        try:
            github_client.post_issue_comment(config.pr_number, body)
        except GitHubAPIError as fallback_exc:
            logger.error("Failed to post fallback comment: %s", fallback_exc)
            return 1

    return 0


def main() -> None:
    config = Config.from_env()
    sys.exit(run(config))


if __name__ == "__main__":
    main()
