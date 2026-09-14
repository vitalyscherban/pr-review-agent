# Contributing

Thanks for considering a contribution to `pr-review-agent`!

## Getting started

```bash
git clone https://github.com/vitalyscherban/pr-review-agent.git
cd pr-review-agent
python -m venv .venv
. .venv/Scripts/activate   # or: source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt -r requirements-dev.txt -e .
```

## Running tests

```bash
pytest
```

All tests mock GitHub and LLM network calls (via the `responses` library and `monkeypatch`) — no real API calls are made, and no credentials are required to run the suite.

## Project layout

- `src/pr_review_agent/` — core package (`config.py`, `diff_utils.py`, `github_client.py`, `llm_client.py`, `reviewer.py`, `main.py`).
- `tests/` — pytest unit tests, one module per source file, plus `fixtures.py` for shared sample data.
- `action.yml` — composite GitHub Action definition.
- `.github/workflows/pr-review.yml` — example workflow that runs the action on `pull_request` events.
- `docs/` — extended documentation.

## Making changes

1. Create a branch for your change.
2. Add or update tests alongside any behavior change — PRs without test coverage for new logic are unlikely to be merged.
3. Run `pytest` locally and ensure it passes.
4. Keep functions small and focused; prefer pure functions (e.g. in `diff_utils.py`, `reviewer.py`) that are easy to unit test without mocking.
5. Open a pull request describing the change and rationale.

## Reporting issues

Please open a GitHub issue with:
- What you expected to happen.
- What actually happened (include relevant workflow logs if applicable).
- Steps to reproduce, if possible.
