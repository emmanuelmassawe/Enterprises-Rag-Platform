# ADR-007: Database-level tenant isolation with RLS

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

Application-level filters can be omitted or misapplied. Tenant isolation is a core security boundary for data, cache, quotas and telemetry.

## Decision

Use PostgreSQL Row-Level Security on tenant-bearing tables plus explicit application filters. Bind tenant and principal IDs transaction-locally from validated auth context, reset safely through transaction/pool lifecycle, use non-owner runtime roles without `BYPASSRLS`, and run migrations under separate credentials. Apply ACL filters before ranking.

## Evidence checked

- PostgreSQL's official [Row Security Policies documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) documents default-deny behavior when RLS is enabled without an applicable policy, and notes table owners and roles with `BYPASSRLS` normally bypass policies unless forced.
- pgvector [multitenancy guidance](https://github.com/pgvector/pgvector#filtering) recommends tenant partitioning in cases where shared approximate indexes affect recall; this must be benchmarked alongside RLS.

## Consequences

- Missing app predicates have a second enforcement boundary.
- Connection pooling, background jobs, migrations and table ownership must be designed carefully; adversarial RLS integration tests are mandatory.

