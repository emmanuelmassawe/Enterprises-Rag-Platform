# ADR-002: REST, SSE and asynchronous jobs

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

The product has stable resources, browser UI and machine API clients, with one streaming response and long-running ingestion. OpenAPI must be the source of truth.

## Decision

Use REST/HTTPS under `/v1`, RFC 9457 errors, cursor pagination, `202` job resources for ingestion, and SSE for query streaming. GraphQL is deferred because there is no demonstrated need for client-defined joins; gRPC is deferred because browser interoperability and human-readable HTTP contracts matter more. SSE has a versioned `rag.query.v1` event contract in the OpenAPI extension. It is not resumable in v1; clients retry explicitly.

## Evidence checked

- OpenAPI 3.1 is the chosen contract format (specification at [spec.openapis.org](https://spec.openapis.org/oas/v3.1.1.html)). OpenAPI 3.1 does not standardize named SSE event payload schemas; a custom extension is used, with an AsyncAPI or contract-test follow-up before implementation.
- API patterns, routes and payloads are project design decisions, not provider facts.

## Consequences

- Simple generated clients and mock server support; SSE uses one-way stream and explicit cancellation.
- A disconnected client cannot resume mid-answer; duplicate query retries may incur cost.
- Contract lint, breaking-change detection and runtime contract tests are required in later milestones.

