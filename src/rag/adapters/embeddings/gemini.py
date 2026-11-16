"""Gemini text embedding adapter with bounded batches and provider timeout."""

from __future__ import annotations

from google import genai
from google.genai import types


class EmbeddingProviderUnavailable(RuntimeError):
    """Provider call or response failed safely and may be retried."""


class GeminiEmbeddings:
    """Create a bounded list of vectors in the configured Gemini embedding space."""

    def __init__(self, api_key: str, model: str, dimensions: int, timeout_seconds: float) -> None:
        self.model = model
        self.dimensions = dimensions
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )

    async def embed(self, contents: list[str]) -> list[list[float]]:
        if not contents:
            return []
        if len(contents) > 100:
            raise ValueError("embedding batch exceeds 100 chunks")
        try:
            response = await self._client.aio.models.embed_content(
                model=self.model,
                contents=[
                    types.Content(parts=[types.Part.from_text(text=content)])
                    for content in contents
                ],
                config=types.EmbedContentConfig(output_dimensionality=self.dimensions),
            )
        except Exception as exc:
            raise EmbeddingProviderUnavailable("embedding provider unavailable") from exc
        vectors = [list(item.values or []) for item in (response.embeddings or [])]
        if len(vectors) != len(contents) or any(
            len(vector) != self.dimensions for vector in vectors
        ):
            raise EmbeddingProviderUnavailable("embedding response shape mismatch")
        return vectors

    async def close(self) -> None:
        await self._client.aio.aclose()
