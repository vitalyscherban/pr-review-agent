from pr_review_agent.config import Config


def test_from_env_defaults_when_missing():
    config = Config.from_env(env={})
    assert config.model == "gpt-4o-mini"
    assert config.strictness == "standard"
    assert config.max_diff_chars == 60_000
    assert config.post_inline_comments is True
    assert config.dry_run is False
    assert config.pr_number == 0


def test_from_env_reads_values():
    env = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "octo/demo",
        "PR_NUMBER": "17",
        "GITHUB_EVENT_NAME": "pull_request",
        "MODEL_NAME": "gpt-4o",
        "MODELS_ENDPOINT": "https://example.test/chat",
        "REVIEW_STRICTNESS": "STRICT",
        "MAX_DIFF_CHARS": "1000",
        "MAX_FILES_IN_PROMPT": "5",
        "POST_INLINE_COMMENTS": "false",
        "DRY_RUN": "true",
    }
    config = Config.from_env(env=env)
    assert config.github_token == "tok"
    assert config.repository == "octo/demo"
    assert config.pr_number == 17
    assert config.model == "gpt-4o"
    assert config.endpoint == "https://example.test/chat"
    assert config.strictness == "strict"
    assert config.max_diff_chars == 1000
    assert config.max_files == 5
    assert config.post_inline_comments is False
    assert config.dry_run is True


def test_from_env_invalid_strictness_falls_back_to_standard():
    config = Config.from_env(env={"REVIEW_STRICTNESS": "bogus"})
    assert config.strictness == "standard"


def test_from_env_invalid_pr_number_defaults_to_zero():
    config = Config.from_env(env={"PR_NUMBER": "not-a-number"})
    assert config.pr_number == 0
