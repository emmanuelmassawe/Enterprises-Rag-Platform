# ADR-006: Separate state and cache Key Value instances

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

Queue/locks/quotas cannot be silently evicted; cache entries may be evicted without correctness impact.

## Decision

Use two separate Render Key Value resources: `rag-state` with `noeviction`, paid persistence where available, and `rag-cache` with `allkeys-lru`, cache persistence off if supported/approved. Keep all keys bounded, TTL'd and tenant/version scoped. Runtime access uses ports and explicit timeouts.

## Evidence checked

- Render [Key Value documentation](https://render.com/docs/key-value) recommends `noeviction` for job queues and `allkeys-lru` for caches. `noeviction` rejects writes at memory limit rather than dropping existing entries. Paid plans support persistence; free plans do not. Render [Blueprint specification](https://render.com/docs/blueprint-spec) exposes `maxmemoryPolicy`, `persistenceMode`, and `ipAllowList` including empty list for internal-only access.
- Current [Render Terraform Registry Key Value resource documentation](https://registry.terraform.io/providers/render-oss/render/1.6.0/docs/resources/keyvalue) documents resource name `render_keyvalue`, policy and connection fields. Re-check latest provider version and schema before `.tf` work; resource schema name has varied by provider release.

## Consequences

- Memory/plan cost is higher than one store, but each data class gets its correct eviction behavior.
- Queue fullness becomes an explicit backpressure event; queue sizing and persistence settings require measured capacity.

