"""Testes para provedor Gemini."""

import types

import ai


class FakeModel:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def generate_content(self, prompt: str):
        assert prompt
        return types.SimpleNamespace(text="Resposta Gemini OK")


def test_ai_manager_uses_gemini_when_configured(monkeypatch) -> None:
    fake_google = types.SimpleNamespace(
        configure=lambda api_key: api_key,
        GenerativeModel=lambda model: FakeModel(model),
    )

    monkeypatch.setattr(ai, "google_generativeai", fake_google, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    manager = ai.AIManager(provider_name="gemini", model="gemini-1.5-flash")

    assert manager.provider.__class__.__name__ == "GoogleGeminiProvider"
    assert manager.get_response("Olá, Gemini!") == "Resposta Gemini OK"
