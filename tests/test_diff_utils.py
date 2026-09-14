from pr_review_agent.diff_utils import build_prompt_diff, parse_diff, truncate_file_diff
from tests.fixtures import SAMPLE_DIFF


def test_parse_diff_returns_expected_number_of_files():
    files = parse_diff(SAMPLE_DIFF)
    assert len(files) == 3
    paths = [f.path for f in files]
    assert paths == ["src/app.py", "src/new_file.py", "assets/logo.png"]


def test_parse_diff_marks_binary_file():
    files = parse_diff(SAMPLE_DIFF)
    binary_file = next(f for f in files if f.path == "assets/logo.png")
    assert binary_file.is_binary is True


def test_parse_diff_marks_new_file():
    files = parse_diff(SAMPLE_DIFF)
    new_file = next(f for f in files if f.path == "src/new_file.py")
    assert new_file.is_new is True


def test_parse_diff_tracks_added_line_numbers():
    files = parse_diff(SAMPLE_DIFF)
    app_file = next(f for f in files if f.path == "src/app.py")
    # Two new lines are added: "return a + b  # fixed" and "def divide..." block (3 add lines total)
    added = app_file.added_line_numbers()
    assert len(added) == 4
    assert added == sorted(added)


def test_parse_diff_empty_input_returns_empty_list():
    assert parse_diff("") == []
    assert parse_diff(None) == []


def test_truncate_file_diff_no_op_when_under_limit():
    text = "short diff"
    assert truncate_file_diff(text, max_chars=100) == text


def test_truncate_file_diff_truncates_and_annotates():
    text = "x" * 500
    result = truncate_file_diff(text, max_chars=100)
    assert result.startswith("x" * 100)
    assert "truncated" in result
    assert "400 more characters" in result


def test_build_prompt_diff_skips_binary_contents():
    files = parse_diff(SAMPLE_DIFF)
    prompt_diff = build_prompt_diff(files, max_files=10, max_file_chars=10_000, max_total_chars=100_000)
    assert "binary file, contents omitted" in prompt_diff
    assert "abcdef1" not in prompt_diff  # raw binary patch content should not appear


def test_build_prompt_diff_respects_max_files():
    files = parse_diff(SAMPLE_DIFF)
    prompt_diff = build_prompt_diff(files, max_files=1, max_file_chars=10_000, max_total_chars=100_000)
    assert "src/app.py" in prompt_diff
    assert "src/new_file.py" not in prompt_diff
    assert "additional changed file(s) omitted" in prompt_diff


def test_build_prompt_diff_respects_total_char_budget():
    files = parse_diff(SAMPLE_DIFF)
    prompt_diff = build_prompt_diff(files, max_files=10, max_file_chars=10_000, max_total_chars=10)
    assert "additional changed file(s) omitted" in prompt_diff
