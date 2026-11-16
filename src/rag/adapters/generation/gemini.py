"""Gemini structured-output adapter for the fixed no-tool answer pipeline."""

from __future__ import annotations

import asyncio
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rag.domain.ports.query import GeneratedClaim, GenerationResult


class GenerationProviderUnavailable(RuntimeError):
    """Provider, safety filter, or structured response failed safely."""


class _Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2_000)
    chunk_ids: list[str] = Field(min_length=1, max_length=20)


class _StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[_Claim] = Field(max_length=20)
    refusal_code: Literal["insufficient_evidence", "policy_refusal"] | None = None


class GeminiAnswerGenerator:
    """Call Gemini asynchronously with JSON-schema output and no tools configured."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        max_concurrency: int,
    ) -> None:
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )

    async def generate(self, system_instruction: str, user_content: str) -> GenerationResult:
        try:
            async with self._semaphore:
                response = await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=user_content,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=_StructuredAnswer,
                        max_output_tokens=self._max_output_tokens,
                        temperature=0.1,
                    ),
                )
        except Exception as exc:
            raise GenerationProviderUnavailable("generation provider unavailable") from exc
        if not response.text:
            raise GenerationProviderUnavailable("generation returned no structured response")
        try:
            parsed = _StructuredAnswer.model_validate_json(response.text)
        except ValidationError as exc:
            raise GenerationProviderUnavailable("generation response did not match schema") from exc
        usage = response.usage_metadata
        candidate = response.candidates[0] if response.candidates else None
        finish_reason = (
            getattr(candidate.finish_reason, "name", str(candidate.finish_reason)).lower()
            if candidate is not None and candidate.finish_reason is not None
            else None
        )
        return GenerationResult(
            claims=tuple(
                GeneratedClaim(claim.text, tuple(claim.chunk_ids)) for claim in parsed.claims
            ),
            refusal_code=parsed.refusal_code,
            input_tokens=usage.prompt_token_count if usage and usage.prompt_token_count else 0,
            output_tokens=usage.candidates_token_count
            if usage and usage.candidates_token_count
            else 0,
            finish_reason=finish_reason,
        )

    async def close(self) -> None:
        await self._client.aio.aclose()
