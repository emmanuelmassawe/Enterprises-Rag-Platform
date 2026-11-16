"""Run the synthetic golden set against a non-production RAG API target."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rag.domain.evaluation import (
    citation_accuracy,
    mean,
    refusal_accuracy,
    retrieval_metrics,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "tests" / "eval" / "golden_dataset.json"
THRESHOLDS_PATH = ROOT / "tests" / "eval" / "thresholds.json"
REPORT_PATH = ROOT / "artifacts" / "eval" / "latest-report.json"


class EvalExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=8_000)
    expected_sources: list[str] = Field(max_length=20)
    reference_answer: str = Field(min_length=1, max_length=4_000)
    expected_refusal: bool = False


class JudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groundedness: float = Field(ge=0, le=1)
    answer_relevance: float = Field(ge=0, le=1)


class GeminiJudge:
    """LLM-as-judge port implementation using the configured Gemini provider."""

    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self.model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1_000)),
        )

    def score(
        self,
        question: str,
        answer: str,
        reference_answer: str,
        evidence: Sequence[str],
    ) -> JudgeResult:
        """Score answer grounding and relevance from synthetic benchmark content."""
        prompt = json.dumps(
            {
                "task": (
                    "Score grounding as the fraction of answer claims supported by evidence; "
                    "score relevance as how directly the answer addresses the question and "
                    "matches the reference answer. Return scores between 0 and 1."
                ),
                "question": question,
                "answer": answer,
                "reference_answer": reference_answer,
                "evidence": list(evidence),
            },
            ensure_ascii=True,
        )
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JudgeResult,
                max_output_tokens=256,
                temperature=0,
            ),
        )
        if not response.text:
            raise RuntimeError("LLM judge returned no structured result")
        try:
            return JudgeResult.model_validate_json(response.text)
        except ValidationError as exc:
            raise RuntimeError("LLM judge returned an invalid score") from exc

    def close(self) -> None:
        self._client.close()


class ApiTarget:
    """Bounded synchronous adapter for the existing admin query endpoint."""

    def __init__(self, base_url: str, api_key: str, collection_id: str) -> None:
        self.collection_id = collection_id
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(45.0, connect=5.0),
            follow_redirects=False,
        )

    def query(self, question: str) -> dict[str, Any]:
        """Call the bounded, non-streaming admin query endpoint with retrieval details."""
        response = self._client.post(
            "/v1/query",
            json={
                "question": question,
                "collection_ids": [self.collection_id],
                "stream": False,
                "debug": True,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("query endpoint returned a non-object response")
        return payload

    def close(self) -> None:
        self._client.close()


def _load_examples() -> tuple[str, str, list[EvalExample]]:
    raw = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("examples"), list):
        raise ValueError("golden dataset must contain an examples array")
    examples = [EvalExample.model_validate(item) for item in raw["examples"]]
    if not examples or len({item.id for item in examples}) != len(examples):
        raise ValueError("golden dataset must be non-empty and have unique example IDs")
    return str(raw["dataset_version"]), str(raw["pipeline_version"]), examples


def _source_ids(value: object, key: str) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    items = value.get(key, [])
    if not isinstance(items, list):
        return []
    return [str(item) for item in items]


def _prediction(payload: dict[str, Any]) -> dict[str, Any]:
    debug = payload.get("retrieval_debug")
    retrieved = debug.get("retrieved", []) if isinstance(debug, dict) else []
    ranked = [
        str(item["chunk_id"]) for item in retrieved if isinstance(item, dict) and "chunk_id" in item
    ]
    citations = payload.get("citations", [])
    cited = [
        str(item["chunk_id"]) for item in citations if isinstance(item, dict) and "chunk_id" in item
    ]
    return {
        "answer": str(payload.get("answer", "")),
        "ranked_sources": ranked,
        "cited_sources": cited,
        "refused": payload.get("refusal") is not None,
        "evidence": [str(item.get("quote", "")) for item in citations if isinstance(item, dict)],
    }


def _score_example(
    example: EvalExample, prediction: dict[str, Any], judge: GeminiJudge, k: int
) -> dict[str, float]:
    metrics = retrieval_metrics(example.expected_sources, prediction["ranked_sources"], k)
    metrics["citation_accuracy"] = citation_accuracy(
        example.expected_sources, prediction["cited_sources"]
    )
    metrics["refusal_accuracy"] = refusal_accuracy(example.expected_refusal, prediction["refused"])
    judged = judge.score(
        example.question,
        prediction["answer"],
        example.reference_answer,
        prediction["evidence"],
    )
    metrics["groundedness"] = judged.groundedness
    metrics["answer_relevance"] = judged.answer_relevance
    return metrics


def _load_thresholds() -> dict[str, float]:
    raw = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("evaluation thresholds must be a JSON object")
    allowed = {
        "recall_at_k",
        "mrr",
        "ndcg",
        "groundedness",
        "answer_relevance",
        "citation_accuracy",
        "refusal_accuracy",
    }
    return {key: float(raw[key]) for key in allowed if raw.get(key) is not None}


def _publish_langsmith(
    examples: Sequence[EvalExample],
    predictions: dict[str, dict[str, Any]],
    scores: dict[str, dict[str, float]],
    dataset_version: str,
    pipeline_version: str,
) -> str | None:
    api_key = os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        return None
    from langsmith import Client, evaluate

    project = os.getenv("LANGSMITH_PROJECT", "rag-evaluation")
    client = Client(api_key=api_key, api_url=os.getenv("LANGSMITH_ENDPOINT") or None)
    by_id = {example.id: example for example in examples}

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        case_id = str(inputs["case_id"])
        return {**predictions[case_id], "metrics": scores[case_id]}

    def metric_evaluator(metric_name: str) -> Any:
        def evaluator(run: Any, _example: Any) -> dict[str, Any]:
            metric_scores = run.outputs["metrics"]
            return {"key": metric_name, "score": float(metric_scores[metric_name])}

        return evaluator

    data = [
        {
            "inputs": {"case_id": example.id, "question": example.question},
            "outputs": {
                "expected_sources": example.expected_sources,
                "reference_answer": example.reference_answer,
                "expected_refusal": example.expected_refusal,
            },
        }
        for example in by_id.values()
    ]
    experiment = evaluate(
        target,
        data=data,
        evaluators=[metric_evaluator(name) for name in next(iter(scores.values()))],
        client=client,
        experiment_prefix=f"{project}-eval-{dataset_version}",
        metadata={"dataset_version": dataset_version, "pipeline_version": pipeline_version},
        max_concurrency=1,
        upload_results=True,
    )
    return str(getattr(experiment, "url", "LangSmith experiment submitted"))


def main() -> int:
    try:
        base_url = os.environ["RAG_EVAL_BASE_URL"]
        api_key = os.environ["RAG_EVAL_API_KEY"]
        collection_id = os.environ["RAG_EVAL_COLLECTION_ID"]
        judge_key = os.environ.get("RAG_EVAL_JUDGE_API_KEY") or os.environ["EMBEDDING_API_KEY"]
    except KeyError as exc:
        sys.stderr.write(f"Missing required evaluation environment variable: {exc.args[0]}\n")
        return 2
    dataset_version, pipeline_version, examples = _load_examples()
    k = int(os.getenv("RAG_EVAL_K", "8"))
    target = ApiTarget(base_url, api_key, collection_id)
    judge = GeminiJudge(
        judge_key,
        os.getenv("RAG_EVAL_JUDGE_MODEL", "gemini-3.8-flash"),
        float(os.getenv("RAG_EVAL_TIMEOUT_SECONDS", "30")),
    )
    rows: list[dict[str, Any]] = []
    predictions: dict[str, dict[str, Any]] = {}
    scores: dict[str, dict[str, float]] = {}
    try:
        for example in examples:
            prediction = _prediction(target.query(example.question))
            predictions[example.id] = prediction
            score = _score_example(example, prediction, judge, k)
            scores[example.id] = score
            rows.append({"example_id": example.id, "metrics": score})
    finally:
        target.close()
        judge.close()
    metric_names = sorted(next(iter(scores.values())))
    aggregate = {name: mean([row[name] for row in scores.values()]) for name in metric_names}
    thresholds = _load_thresholds()
    failures = {
        name: {"actual": aggregate.get(name), "minimum": minimum}
        for name, minimum in thresholds.items()
        if aggregate.get(name, -1.0) < minimum
    }
    report: dict[str, Any] = {
        "dataset_version": dataset_version,
        "pipeline_version": pipeline_version,
        "k": k,
        "example_count": len(examples),
        "metrics": aggregate,
        "thresholds": thresholds,
        "threshold_failures": failures,
        "examples": rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    experiment_url = _publish_langsmith(
        examples, predictions, scores, dataset_version, pipeline_version
    )
    sys.stdout.write(json.dumps({**report, "langsmith_experiment": experiment_url}, indent=2))
    sys.stdout.write("\n")
    if not thresholds:
        sys.stdout.write(
            "No owner-approved thresholds configured; this run records a baseline only.\n"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
