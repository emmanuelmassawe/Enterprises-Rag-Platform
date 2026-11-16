from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rag.adapters.generation import gemini
from rag.adapters.generation.gemini import GeminiAnswerGenerator, GenerationProviderUnavailable


class _Models:
    def __init__(self, text: str) -> None:
        self.text = text
        self.kwargs: dict[str, object] = {}

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            text=self.text,
            usage_metadata=SimpleNamespace(prompt_token_count=24, candidates_token_count=9),
        )


class _Aio:
    def __init__(self, models: _Models) -> None:
        self.models = models
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _Client:
    def __init__(self, models: _Models) -> None:
        self.aio = _Aio(models)


@pytest.mark.asyncio
async def test_gemini_adapter_uses_schema_no_tools_and_returns_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _Models(
        json.dumps(
            {
                "claims": [{"text": "Supported claim.", "chunk_ids": ["chunk-1"]}],
                "refusal_code": None,
            }
        )
    )
    client = _Client(models)
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: client)
    generator = GeminiAnswerGenerator("test-key", "gemini-3.8-flash", 5, 256, 2)

    result = await generator.generate("system", "user")

    assert result.claims[0].chunk_ids == ("chunk-1",)
    assert result.input_tokens == 24 and result.output_tokens == 9
    config = models.kwargs["config"]
    assert config.response_schema is not None
    assert not models.kwargs.get("tools")
    await generator.close()
    assert client.aio.closed


@pytest.mark.asyncio
async def test_gemini_adapter_rejects_invalid_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(_Models("not-json"))
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: client)
    generator = GeminiAnswerGenerator("test-key", "model", 5, 256, 1)

    with pytest.raises(GenerationProviderUnavailable, match="did not match schema"):
        await generator.generate("system", "user")
