# ADR-016: Versioned synthetic evaluation harness

- Status: proposed for Milestone 6; owner approval pending at milestone review
- Date: 2026-11-16
- Context: FR-EVL-001 requires a reproducible golden set, retrieval and answer metrics, and a regression gate. The brief also requires LangSmith datasets and experiments. No owner-approved quality thresholds or non-production evaluation tenant are recorded yet.

## Decision

Keep evaluation separate from request handling. `src/rag/domain/evaluation.py` contains deterministic, provider-free scoring for recall@k, MRR, nDCG, citation accuracy and refusal accuracy. `scripts/evaluate.py` calls the existing admin-only debug query endpoint in a configured non-production environment and sends only the synthetic versioned benchmark to a Gemini judge for groundedness and answer relevance. The Gemini call uses a Pydantic response schema, explicit timeout, no tools, and bounded output.

When `LANGSMITH_API_KEY` is configured, the same synthetic examples, cached predictions and scores are submitted through the standalone LangSmith SDK `evaluate()` experiment API. Without that key, the local JSON report still runs. LangSmith remains optional for local baseline runs; any configured LangSmith submission error fails the command rather than silently claiming an experiment was recorded.

`tests/eval/thresholds.json` starts with unset thresholds. This permits baseline measurement without inventing quality targets. Once an owner reviews and approves metric floors, setting a numeric floor makes `make eval` exit nonzero on regression. Dataset, pipeline and judge model versions are recorded in reports/experiment metadata. The evaluation target must use synthetic or licensed content and must never be production.

## Consequences

- Evaluation code is separate from query business logic and unit-testable without network or LLM calls.
- Retrieval rank metrics use the admin debug endpoint's ranked chunk IDs; each non-production benchmark collection must preserve the source IDs recorded in the synthetic golden set.
- LLM-as-judge scores are advisory measures and require calibration against human review before quality gates are approved.
- A baseline cannot be reproduced until the owner or operator provides the configured synthetic collection, admin key, target URL and judge credentials.
- Generated reports are local ignored artifacts; LangSmith gets only synthetic question, answer, evidence quote, expected source identifiers and scores.

## Verification

Unit tests cover metric calculations and dataset versioning without network calls. The full evaluation requires explicit `RAG_EVAL_*` settings and a non-production collection. Thresholds remain unapproved until reviewed by the owner.

## References checked 2026-11-16

- LangSmith `evaluate()` supports a target function, inline example data, evaluators, experiment metadata, concurrency bounds and uploading results: [LangSmith Python reference: evaluate](https://reference.langchain.com/python/langsmith/evaluation/_runner/evaluate).
- LangSmith recommends curated offline datasets for benchmarking and distinguishes deterministic code evaluators from LLM-as-judge evaluation: [LangSmith evaluation types](https://docs.langchain.com/langsmith/evaluation-types).
- Google GenAI Python SDK supports `client.models.generate_content` and Pydantic response schemas: [Google Gen AI SDK documentation](https://googleapis.github.io/python-genai/) and [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).
