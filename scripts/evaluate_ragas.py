"""Optional local-Ollama RAGAS scoring for persisted evaluation runs.

Install the optional dependencies from requirements-evaluation.txt first. This
script scores only rows already present in the local result files and uses the
local Ollama API; failures are written to the report and produce a nonzero exit.
"""

import argparse
import asyncio
import inspect
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
os.environ["RAGAS_DO_NOT_TRACK"] = "true"
os.environ["LANGCHAIN_TRACING_V2"] = "false"


def _load_results(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("dataset_id") != "enterprise-rag-v1" or data.get("dataset_version") != 1:
        raise ValueError(f"Unsupported or unversioned evaluation dataset in {path.name}")
    return data


def _latest_complete_evaluation(directory: Path) -> Path:
    """Select the newest complete timestamped evaluation, never a legacy alias."""
    for path in sorted(directory.glob("enterprise_rag_evaluation_*Z.json"), reverse=True):
        try:
            data = _load_results(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if (
            data.get("execution_status") == "completed"
            and data.get("failed_case_count") == 0
            and data.get("completed_case_count") == data.get("case_count")
        ):
            return path
    raise FileNotFoundError(
        f"No complete timestamped evaluation JSON found in {directory}; "
        "run scripts/evaluate_rag.py first or pass --improved explicitly."
    )


def _timestamped_output_path(directory: Path, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    base = directory / f"ragas_comparison_{timestamp}.json"
    if not base.exists():
        return base
    counter = 2
    while (candidate := directory / f"ragas_comparison_{timestamp}_{counter}.json").exists():
        counter += 1
    return candidate


def _evaluation_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for case_index, row in enumerate(data.get("results", []), start=1):
        if row.get("case_status") not in (None, "completed"):
            continue
        answer = row.get("answer")
        contexts = row.get("retrieved_contexts")
        reference = row.get("reference_answer_approximate")
        if (
            row.get("error") or row.get("generation_error")
            or not isinstance(answer, str) or not isinstance(contexts, list)
            or not contexts or not all(isinstance(item, str) for item in contexts)
            or not isinstance(reference, str) or not reference
        ):
            continue
        rows.append({
            "case_index": case_index,
            "user_input": str(row["question"]),
            "response": answer,
            "retrieved_contexts": contexts,
            "reference": reference,
        })
    return rows


def _make_local_ollama_ragas_llm(
    model: str,
    base_url: str,
    *,
    client_class: Any = None,
    ragas_llm_factory: Any = None,
) -> tuple[Any, Any]:
    """Build a RAGAS LLM adapter over Ollama's local OpenAI-compatible endpoint."""
    if client_class is None:
        from openai import AsyncOpenAI

        client_class = AsyncOpenAI
    if ragas_llm_factory is None:
        from ragas.llms import llm_factory

        ragas_llm_factory = llm_factory

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1", "localhost", "::1",
    }:
        raise ValueError("RAGAS Ollama endpoint must use a local loopback address")
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint += "/v1"

    # RAGAS 0.4 requires an explicit client. `provider='openai'` selects its
    # OpenAI-compatible adapter; the client is still pointed only at local Ollama.
    client = client_class(api_key="ollama", base_url=endpoint)
    return ragas_llm_factory(
        model,
        provider="openai",
        client=client,
        reasoning_effort="none",
    ), client


async def _score_metric(metric: Any, row: dict[str, Any]) -> Any:
    """Pass only fields declared by the selected RAGAS metric."""
    accepted_fields = inspect.signature(metric.ascore).parameters
    metric_row = {key: value for key, value in row.items() if key in accepted_fields}
    return await metric.ascore(**metric_row)


async def _score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from ragas.embeddings import HuggingFaceEmbeddings
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
        Faithfulness,
    )

    model = os.getenv("RAG_EVAL_JUDGE_MODEL", os.getenv("OLLAMA_MODEL", "qwen3.5:4b"))
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    llm, client = _make_local_ollama_ragas_llm(model, base_url)
    embeddings = HuggingFaceEmbeddings(
        model="BAAI/bge-large-en-v1.5", normalize_embeddings=True,
    )
    metrics = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_precision": ContextPrecisionWithReference(llm=llm),
        "context_recall": ContextRecall(llm=llm),
    }
    results = []
    try:
        for row in rows:
            scores: dict[str, float | None] = {}
            failures = []
            for name, metric in metrics.items():
                try:
                    value = await _score_metric(metric, row)
                    score = value.value
                    if score is None:
                        raise ValueError("metric returned no score")
                    scores[name] = float(score)
                except Exception as exc:  # noqa: BLE001 - record per-metric failure without payloads.
                    scores[name] = None
                    failures.append({"metric": name, "category": type(exc).__name__})
            results.append({
                "case_index": row["case_index"],
                "metric_scores": scores,
                "failures": failures,
            })
    finally:
        await client.close()
    return results


def _score_run(data: dict[str, Any], label: str, source_file: Path) -> dict[str, Any]:
    rows = _evaluation_rows(data)
    if not rows:
        raise ValueError(f"No usable answer/context samples in {label} run")
    case_results = asyncio.run(_score_rows(rows))
    aggregate = {
        name: (
            round(sum(scores) / len(scores), 6) if scores else None
        )
        for name in METRICS
        for scores in [[
            item["metric_scores"][name]
            for item in case_results
            if item["metric_scores"][name] is not None
        ]]
    }
    failures = sum(len(item["failures"]) for item in case_results)
    return {
        "label": label,
        "source_file": source_file.name,
        "case_count": len(rows),
        "scores": aggregate,
        "metric_failure_count": failures,
        "case_results": case_results,
        "model_snapshot": {
            "judge": os.getenv("RAG_EVAL_JUDGE_MODEL", os.getenv("OLLAMA_MODEL", "qwen3.5:4b")),
            "provider": "ollama",
            "embedding": "BAAI/bge-large-en-v1.5",
            "dataset_id": data.get("dataset_id"),
            "dataset_version": data.get("dataset_version"),
            "source_evaluation_created_at_utc": data.get("created_at_utc"),
            "generation_model": data.get("model_snapshot", {}).get("generation_model"),
            "reranker_model": data.get("model_snapshot", {}).get("reranker_model"),
            "retrieval_top_k": data.get("top_k"),
            "reranker_score_threshold": data.get("reranker_score_threshold"),
            "reranker_score_threshold_source": data.get("reranker_score_threshold_source"),
        },
    }


def _score_run_safely(data: dict[str, Any], label: str, source_file: Path) -> dict[str, Any]:
    try:
        return _score_run(data, label, source_file)
    except Exception as exc:  # noqa: BLE001 - persist category only; never log data.
        return {
            "label": label,
            "source_file": source_file.name,
            "case_count": len(data.get("results", [])),
            "scores": {name: None for name in METRICS},
            "failure": {"category": type(exc).__name__},
            "model_snapshot": {
                "judge": os.getenv("RAG_EVAL_JUDGE_MODEL", os.getenv("OLLAMA_MODEL", "qwen3.5:4b")),
                "provider": "ollama",
                "embedding": "BAAI/bge-large-en-v1.5",
                "dataset_id": data.get("dataset_id"),
                "dataset_version": data.get("dataset_version"),
                "source_evaluation_created_at_utc": data.get("created_at_utc"),
                "generation_model": data.get("model_snapshot", {}).get("generation_model"),
                "reranker_model": data.get("model_snapshot", {}).get("reranker_model"),
                "retrieval_top_k": data.get("top_k"),
                "reranker_score_threshold": data.get("reranker_score_threshold"),
                "reranker_score_threshold_source": data.get("reranker_score_threshold_source"),
            },
        }


def _has_scoring_failure(runs: list[dict[str, Any]]) -> bool:
    return any(
        run.get("failure") or run.get("metric_failure_count", 0)
        or any(value is None for value in run.get("scores", {}).values())
        for run in runs
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--improved", type=Path,
        help="Versioned RAG evaluation JSON (defaults to the latest complete timestamped run)",
    )
    parser.add_argument("--baseline", type=Path, help="Optional compatible baseline JSON for side-by-side comparison")
    parser.add_argument("--output", type=Path, help="Output JSON (defaults to a new timestamped file)")
    args = parser.parse_args()

    evaluation_dir = PROJECT_ROOT / "reports/evaluation"
    improved_path = args.improved or _latest_complete_evaluation(evaluation_dir)
    output_path = args.output or _timestamped_output_path(evaluation_dir)
    improved_data = _load_results(improved_path)
    runs = []
    if args.baseline:
        runs.append(_score_run_safely(_load_results(args.baseline), "baseline", args.baseline))
    runs.append(_score_run_safely(improved_data, "improved", improved_path))
    comparison = {"baseline": None, "improved": runs[-1]["scores"]}
    if len(runs) == 2:
        comparison["baseline"] = runs[0]["scores"]
    deltas = {
        key: (
            round(comparison["improved"][key] - comparison["baseline"][key], 6)
            if comparison["baseline"] is not None
            and comparison["improved"].get(key) is not None
            and comparison["baseline"].get(key) is not None else None
        )
        for key in comparison["improved"]
    }
    report = {
        "evaluation": "optional RAGAS local Ollama estimate",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "comparison": comparison,
        "deltas": deltas,
        "runs": runs,
        "limitations": [
            "RAGAS scores are model-based estimates and are not proof of correctness or citation entailment.",
            "References are generated from expected-fact phrases and are approximate; context metrics should be interpreted cautiously.",
            "Baseline deltas are meaningful only for matching dataset and evaluator configurations.",
            "Evaluation runs locally through Ollama; no external provider is configured.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    improved_snapshot = runs[-1]["model_snapshot"]
    markdown = [
        "# Optional RAGAS Evaluation", "",
        f"Dataset: `{improved_data['dataset_id']}` v{improved_data['dataset_version']}",
        f"Source evaluation: `{improved_path.name}` ({improved_snapshot['source_evaluation_created_at_utc']})",
        f"Judge: `{improved_snapshot['provider']} / {improved_snapshot['judge']}`; embedding: `{improved_snapshot['embedding']}`",
        f"Generation model: `{improved_snapshot['generation_model']}`; reranker: `{improved_snapshot['reranker_model']}`",
        f"Retrieval top K: `{improved_snapshot['retrieval_top_k']}`; reranker threshold: `{improved_snapshot['reranker_score_threshold']}` ({improved_snapshot['reranker_score_threshold_source']})",
        "", "| Run | Cases | Metric failures | Faithfulness | Answer relevancy | Context precision | Context recall |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for run in runs:
        scores = run["scores"]
        markdown.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            run["label"], run["case_count"], run.get("metric_failure_count", "unknown"),
            *(scores[key] for key in METRICS),
        ))
    markdown.extend(["", "Scores are local model estimates, not proof of correctness or entailment. Any null metric or failed run is recorded; this command exits nonzero if scoring is incomplete.", ""])
    output_path.with_suffix(".md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "comparison": comparison,
        "deltas": deltas,
        "runs": [
            {
                "label": run["label"],
                "source_file": run["source_file"],
                "case_count": run["case_count"],
                "metric_failure_count": run.get("metric_failure_count"),
                "failure": run.get("failure"),
            }
            for run in runs
        ],
    }, indent=2))
    if _has_scoring_failure(runs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
