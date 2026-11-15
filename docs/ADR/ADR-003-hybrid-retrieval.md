# ADR-003: Hybrid retrieval with RRF

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

English PDF queries need semantic and exact-term matching. A single retrieval method may miss either paraphrases or exact policy phrases.

## Decision

Use pgvector dense retrieval and PostgreSQL full-text search, merge ranked lists with Reciprocal Rank Fusion, and make reranking optional behind a port. Keep query rewriting disabled by default unless evaluation demonstrates net quality gain. Retrieval and generation are measured independently.

## Evidence checked

- The [pgvector documentation](https://github.com/pgvector/pgvector) covers vector distance operators, HNSW/IVFFlat, search tuning, and filtered ANN behavior. It does not prescribe RRF; RRF is a project-level, testable choice.

## Consequences

- Supports exact terms and semantic similarity in one primary database.
- RRF weights, candidate counts, filters and optional reranking require golden-set evaluation.
- Do not declare quality thresholds until baseline results and owner review.

