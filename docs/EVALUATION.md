# Evaluation

The benchmark in `tests/eval/golden_dataset.json` contains synthetic policy questions, expected answer references, source chunk IDs, and refusal expectations. Dataset and pipeline versions are explicit. Do not add real customer queries, retrieved customer text, identifiers, or answers to this repository.

## Run against a non-production collection

The environment must contain the synthetic corpus represented by the dataset, with the expected source chunk IDs intact. Use an admin API key scoped to that benchmark tenant and collection. Set:

| Variable | Purpose |
|---|---|
| `RAG_EVAL_BASE_URL` | Non-production API URL. |
| `RAG_EVAL_API_KEY` | Admin key for that evaluation tenant only. |
| `RAG_EVAL_COLLECTION_ID` | Synthetic benchmark collection UUID. |
| `EMBEDDING_API_KEY` or `RAG_EVAL_JUDGE_API_KEY` | Gemini judge credential; the dedicated evaluation key is preferred. |
| `RAG_EVAL_JUDGE_MODEL` | Judge model, default `gemini-3.8-flash`. |
| `RAG_EVAL_TIMEOUT_SECONDS` | Judge timeout, default 30 seconds. |
| `RAG_EVAL_K` | Retrieval cutoff, default 8. |
| `LANGSMITH_API_KEY` | Optional key to publish a LangSmith experiment. |
| `LANGSMITH_PROJECT` | Optional experiment project, default `rag-evaluation`. |
| `LANGSMITH_ENDPOINT` | Optional LangSmith regional API endpoint. |

Then run `make eval`. The command calls `POST /v1/query` with `debug=true`, scores returned retrieval chunk IDs and citations, invokes the LLM judge, writes an ignored local report to `artifacts/eval/latest-report.json`, and optionally records the same synthetic experiment in LangSmith. The evaluation endpoint is admin-only and the configured API key must have the admin role.

The dataset's source IDs are benchmark identifiers. Before running against a newly populated benchmark collection, verify those IDs against its ingestion results and revise the dataset version if the corpus changes. Do not use production credentials or collections.

## Threshold governance

`tests/eval/thresholds.json` intentionally has no numeric floors yet. The first successful run is a baseline, not a quality claim. The owner should review per-example scores and LLM judge samples, then approve numeric floors in a reviewed change. Once set, `make eval` fails if an aggregate score falls below a configured floor. No gate may be inferred from an unset threshold.

See [ADR-016](ADR/ADR-016-milestone-6-evaluation-harness.md) for the architecture and provider references.
