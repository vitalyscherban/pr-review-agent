# Configuration

All configuration is supplied either as GitHub Action `inputs` (see [`action.yml`](../action.yml)) or as environment variables read by `pr_review_agent.config.Config.from_env`. Workflow inputs are mapped to environment variables by the composite action.

| Action input | Environment variable | Default | Type | Description |
| --- | --- | --- | --- | --- |
| `github-token` | `GITHUB_TOKEN` | `${{ github.token }}` | string | Token used for both the GitHub REST API and the GitHub Models inference endpoint. Must have `pull-requests: write` and `models: read` permissions granted to the workflow. |
| `pr-number` | `PR_NUMBER` | `${{ github.event.pull_request.number }}` | integer | The pull request number to review. |
| — | `GITHUB_REPOSITORY` | set automatically by Actions | string | `owner/repo` slug used to build API URLs. |
| — | `GITHUB_EVENT_NAME` | set automatically by Actions | string | Name of the triggering event (informational). |
| `model` | `MODEL_NAME` | `gpt-4o-mini` | string | GitHub Models model identifier to request. |
| `models-endpoint` | `MODELS_ENDPOINT` | `https://models.inference.ai.azure.com/chat/completions` | string | Chat-completions endpoint URL. |
| `strictness` | `REVIEW_STRICTNESS` | `standard` | `lenient` \| `standard` \| `strict` | Controls how aggressively the LLM is instructed to flag issues. Invalid values fall back to `standard`. |
| `post-inline-comments` | `POST_INLINE_COMMENTS` | `true` | boolean (`true`/`false`) | Whether to attach inline comments to specific diff lines in addition to the summary review. |
| `max-diff-chars` | `MAX_DIFF_CHARS` | `60000` | integer | Total character budget for the diff text included in the LLM prompt. |
| — | `MAX_FILES_IN_PROMPT` | `60` | integer | Maximum number of changed files included in the prompt before the rest are summarized as omitted. |
| `dry-run` | `DRY_RUN` | `false` | boolean | When `true`, prints the review to stdout instead of calling the GitHub API. Useful for local testing / CI dry runs. |

## Repository variables

The bundled `.github/workflows/pr-review.yml` also reads optional repository variables so you can change defaults without editing the workflow file:

- `vars.PR_REVIEW_MODEL` — overrides the default model.
- `vars.PR_REVIEW_STRICTNESS` — overrides the default strictness.

## Strictness levels

- **lenient** — only flags clear bugs, security vulnerabilities, or serious problems; avoids nitpicking style.
- **standard** (default) — balanced: bugs, security concerns, notable quality issues, and significant style problems.
- **strict** — thorough: also flags style inconsistencies, missing tests, and missing documentation.
