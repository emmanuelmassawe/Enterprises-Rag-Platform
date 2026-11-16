"""Bounded synthetic query load test for an owner-controlled non-production target."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from uuid import UUID

import httpx


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


async def run() -> int:
    base_url = os.environ.get("RAG_LOAD_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("RAG_LOAD_API_KEY", "")
    collection = os.environ.get("RAG_LOAD_COLLECTION_ID", "")
    if not base_url or not api_key or not collection:
        sys.stderr.write("Set RAG_LOAD_BASE_URL, RAG_LOAD_API_KEY, and RAG_LOAD_COLLECTION_ID.\n")
        return 2
    try:
        UUID(collection)
    except ValueError:
        sys.stderr.write("RAG_LOAD_COLLECTION_ID must be a UUID.\n")
        return 2
    request_count = int(os.environ.get("RAG_LOAD_REQUESTS", "100"))
    concurrency = int(os.environ.get("RAG_LOAD_CONCURRENCY", "10"))
    if not 1 <= request_count <= 100_000 or not 1 <= concurrency <= 500:
        sys.stderr.write("Request count must be 1..100000 and concurrency 1..500.\n")
        return 2

    durations: list[float] = []
    outcomes: Counter[str] = Counter()
    semaphore = asyncio.Semaphore(concurrency)
    timeout = httpx.Timeout(30.0, connect=3.0)
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:

        async def request_one() -> None:
            async with semaphore:
                start = time.perf_counter()
                try:
                    response = await client.post(
                        f"{base_url}/v1/query",
                        json={
                            "question": "Summarize the available policy information.",
                            "collection_ids": [collection],
                            "stream": False,
                            "top_k": 5,
                        },
                    )
                    durations.append(time.perf_counter() - start)
                    outcomes[str(response.status_code)] += 1
                except httpx.HTTPError:
                    durations.append(time.perf_counter() - start)
                    outcomes["transport_error"] += 1

        await asyncio.gather(*(request_one() for _ in range(request_count)))
    summary = {
        "requests": request_count,
        "concurrency": concurrency,
        "outcomes": dict(outcomes),
        "p50_seconds": round(percentile(durations, 0.50), 3),
        "p95_seconds": round(percentile(durations, 0.95), 3),
        "max_seconds": round(max(durations), 3),
        "mean_seconds": round(statistics.fmean(durations), 3),
    }
    sys.stdout.write(json.dumps(summary, sort_keys=True) + "\n")
    failed = sum(count for code, count in outcomes.items() if not code.startswith("2"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
