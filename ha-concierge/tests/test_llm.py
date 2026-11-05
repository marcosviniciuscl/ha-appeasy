import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm


def test_openrouter_chat_uses_own_key_and_default_model(monkeypatch):
    monkeypatch.setattr(llm, "options", lambda: {"openrouter_api_key": "test-key"})
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": "Tudo certo"}}]}
    monkeypatch.setattr(llm.requests, "post", Mock(return_value=response))
    answer = llm.ask("openrouter", "", "Como está a casa?")
    assert answer == "Tudo certo"
    args, kwargs = llm.requests.post.call_args
    assert args[0] == "https://openrouter.ai/api/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == "openrouter/auto"


def test_openrouter_image_uses_chat_image_part(monkeypatch):
    monkeypatch.setattr(llm, "options", lambda: {"openrouter_api_key": "test-key"})
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": "Porta fechada"}}]}
    monkeypatch.setattr(llm.requests, "post", Mock(return_value=response))
    llm.ask("openrouter", "google/gemini-2.5-flash", "Verifique a entrada", b"image-bytes")
    body = llm.requests.post.call_args.kwargs["json"]
    assert body["model"] == "google/gemini-2.5-flash"
    image = body["messages"][0]["content"][1]
    assert image["type"] == "image_url"
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_openrouter_requires_its_key(monkeypatch):
    monkeypatch.setattr(llm, "options", lambda: {})
    with pytest.raises(RuntimeError, match="chave"):
        llm.ask("openrouter", "", "Oi")
