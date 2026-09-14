# Architecture

This document expands on the architecture diagrams in the [README](../README.md).

## Components

### 1. Workflow trigger (`.github/workflows/pr-review.yml`)

Listens for `pull_request` events with types `opened`, `synchronize`, and `reopened`. Declares the minimal permissions the job needs: `contents: read`, `pull-requests: write` (to post reviews/comments), and `models: read` (to call GitHub Models). Invokes the packaged action (`uses: ./` or `uses: vitalyscherban/pr-review-agent@main`).

### 2. GitHub Action (`action.yml`)

A composite action that sets up Python, installs `requirements.txt`, and runs `python -m pr_review_agent.main` with configuration passed through environment variables derived from the action's `inputs`. This lets the same core logic be consumed either directly (checked out in this repo) or as a reusable action referenced from other repositories.

### 3. `github_client.py`

Thin wrapper around the GitHub REST API using `requests`:
- `get_pr` / `get_pr_diff` — fetch PR metadata and the unified diff (`Accept: application/vnd.github.v3.diff`).
- `post_review` — submits a full PR review (`APPROVE` / `REQUEST_CHANGES` / `COMMENT`) with optional inline comments in one call.
- `post_issue_comment` — a plain top-level comment, used as a fallback (e.g. when a review can't be submitted, such as when the token belongs to the PR author) and for failure notifications.
- Raises `GitHubAPIError` on non-2xx responses, with a specific message for rate-limit (403) responses.

### 4. `diff_utils.py`

Parses a unified diff into structured `FileDiff`/`DiffLine` objects:
- Detects binary files (`Binary files ... differ` / `GIT binary patch`), new files, deleted files, and renames.
- Tracks the **new-file line numbers** for added lines, which is required to anchor inline review comments correctly via the GitHub API.
- `build_prompt_diff` assembles a size-bounded diff string for the LLM prompt: binary file contents are omitted entirely, individual files are truncated past `max_file_chars`, and the overall list stops once `max_files` or `max_total_chars` is reached (with a note about how much was omitted).

### 5. `reviewer.py`

Orchestration layer:
- Builds a system prompt (varies by `strictness`: `lenient` / `standard` / `strict`) instructing the LLM to return a single JSON object with `verdict`, `summary`, and `findings`.
- Builds the user prompt from the PR title/description plus the bounded diff text.
- Calls `llm_client.chat(...)` and parses the response (`parse_llm_response`), tolerating markdown code fences or stray text around the JSON payload, and falling back to a `COMMENT` verdict with the raw text as the summary if JSON parsing fails entirely.
- Converts findings that reference a file/line into `InlineComment`s, filtering out any that don't correspond to an actually-added line in the diff (GitHub rejects inline comments on lines outside the diff).
- `ReviewResult.to_markdown()` renders the final PR comment body (verdict badge, summary, bulleted findings with severity emoji).

### 6. `llm_client.py`

Calls the GitHub Models OpenAI-compatible chat-completions endpoint (`https://models.inference.ai.azure.com/chat/completions` by default) using the workflow's `GITHUB_TOKEN` as the bearer token. Raises `LLMError` for network failures, rate limits (429), non-2xx responses, or unexpected response shapes.

### 7. `main.py`

The action's entrypoint:
- Builds `Config` from environment variables.
- Fetches PR metadata + diff, calls `review_diff`, and posts the resulting review.
- On LLM failure, posts a comment explaining the failure and exits non-zero (so the workflow run is visibly marked failed) rather than crashing silently or leaving the PR without any feedback.
- Falls back to a plain issue comment if posting a full review fails (e.g. GitHub's "can't approve/request changes on your own PR" restriction), so the review content is never lost.
- Supports a `dry-run` mode that prints the review to stdout instead of calling the GitHub API, useful for local testing.

## Data flow summary

1. GitHub emits a `pull_request` event.
2. The workflow checks out the repo and runs the action.
3. The action fetches the PR diff and metadata via the GitHub REST API.
4. The diff is parsed and bounded, then sent to GitHub Models with review instructions.
5. GitHub Models returns a structured JSON verdict + findings.
6. The agent renders markdown and posts it as a PR review (with inline comments where applicable) back to GitHub, which the PR author sees.
