# ADR-008: Gemini behind provider ports in a fixed, no-tool RAG pipeline

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

Owner prefers Gemini API and Gemini embeddings. The product's scope is retrieval and grounded answers, not an agent. No model IDs, embedding dimension, endpoint/region, SDK, pricing cap or data-use terms have been selected.

## Decision

Define `LLMProvider` and `EmbeddingProvider` ports with a Gemini adapter as the initial candidate after current official docs and privacy terms are verified. Keep the LLM tool-free, with bounded token/context budgets, provider timeouts and circuit breaker, strict structured output, citation verification, refusal threshold and output scanning. Do not choose an exact model or threshold in Phase 0.

## Evidence checked

- Current Gemini API, SDK signatures, model availability, embedding dimension, region, data retention and pricing are **not verified in this ADR**. Before implementation, check official [Gemini API documentation](https://ai.google.dev/gemini-api/docs) and applicable Google terms for the selected account/tier; record model ID/version and actual contract terms.
- RAG security controls derive from BRIEF §5A and require red-team evidence, not model claims.

## Consequences

- Owner preference is preserved without embedding vendor assumptions in services.
- API compatibility, language support and data handling remain blocking verification items before external calls.
- No tools reduce blast radius but do not eliminate prompt injection or hallucination risk.

