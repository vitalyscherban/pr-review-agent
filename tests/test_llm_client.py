import pytest
import responses

from pr_review_agent.llm_client import LLMClient, LLMError

ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"


@pytest.fixture
def client():
    return LLMClient(token="fake-token", model="gpt-4o-mini", endpoint=ENDPOINT)


@responses.activate
def test_chat_returns_message_content(client):
    responses.add(
        responses.POST,
        ENDPOINT,
        json={"choices": [{"message": {"content": "Looks good!"}}]},
        status=200,
    )
    result = client.chat("system prompt", "user prompt")
    assert result == "Looks good!"


@responses.activate
def test_chat_raises_on_rate_limit(client):
    responses.add(responses.POST, ENDPOINT, json={"error": "slow down"}, status=429)
    with pytest.raises(LLMError, match="rate limit"):
        client.chat("system", "user")


@responses.activate
def test_chat_raises_on_server_error(client):
    responses.add(responses.POST, ENDPOINT, json={"error": "boom"}, status=500)
    with pytest.raises(LLMError):
        client.chat("system", "user")


@responses.activate
def test_chat_raises_on_unexpected_response_shape(client):
    responses.add(responses.POST, ENDPOINT, json={"unexpected": "shape"}, status=200)
    with pytest.raises(LLMError, match="Unexpected response shape"):
        client.chat("system", "user")


@responses.activate
def test_chat_sends_expected_payload(client):
    responses.add(
        responses.POST,
        ENDPOINT,
        json={"choices": [{"message": {"content": "ok"}}]},
        status=200,
    )
    client.chat("sys", "usr", temperature=0.5, max_tokens=100)
    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "Bearer fake-token"
    body = sent.body.decode() if isinstance(sent.body, bytes) else sent.body
    assert "gpt-4o-mini" in body
    assert "sys" in body
    assert "usr" in body
