"""Optional local-Ollama RAGAS scoring for persisted evaluation runs.

Install the optional dependencies from requirements-evaluation.txt first. This
script scores only rows already present in the local result files and uses the
local Ollama API; failures are written to the report and produce a nonzero exit.
"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = PROJECT_ROOT / "reports/evaluation/enterprise_rag_evaluation_results.json"
METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
os.environ["RAGAS_DO_NOT_TRACK"] = "true"
os.environ["LANGCHAIN_TRACING_V2"] = "false"


def _load_results(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("dataset_id") != "enterprise-rag-v1" or data.get("dataset_version") != 1:
        raise ValueError(f"Unsupported or unversioned evaluation dataset in {path.name}")
    return data


def _evaluation_rows(data: dict[str, Any]) -> list[dict[str, str | list[str]]]:
    rows = []
    for row in data.get("results", []):
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
            "user_input": str(row["question"]),
            "response": answer,
            "retrieved_contexts": contexts,
            "reference": reference,
        })
    return rows


async def _score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from ragas.embeddings import HuggingFaceEmbeddings
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
        Faithfulness,
    )

    model = os.getenv("RAG_EVAL_JUDGE_MODEL", os.getenv("OLLAMA_MODEL", "qwen3.5:4b"))
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    llm = llm_factory(model, provider="ollama", base_url=base_url)
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
    for row in rows:
        scores: dict[str, float | None] = {}
        failures = []
        for name, metric in metrics.items():
            try:
                value = await metric.ascore(**row)
                score = value.value
                if score is None:
                    raise ValueError("metric returned no score")
                scores[name] = float(score)
            except Exception as exc:  # noqa: BLE001 - record per-metric failure without payloads.
                scores[name] = None
                failures.append({"metric": name, "category": type(exc).__name__})
        results.append({
            "question": row["user_input"],
            "reference_answer_approximate": row["reference"],
            "answer": row["response"],
            "retrieved_contexts": row["retrieved_contexts"],
            "metric_scores": scores,
            "failures": failures,
        })
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
    parser.add_argument("--improved", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--baseline", type=Path, help="Optional compatible baseline JSON for side-by-side comparison")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports/evaluation/ragas_comparison.json")
    args = parser.parse_args()

    improved_data = _load_results(args.improved)
    runs = []
    if args.baseline:
        runs.append(_score_run_safely(_load_results(args.baseline), "baseline", args.baseline))
    runs.append(_score_run_safely(improved_data, "improved", args.improved))
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown = ["# Optional RAGAS Evaluation", "", f"Dataset: `{improved_data['dataset_id']}` v{improved_data['dataset_version']}", "", "| Run | Faithfulness | Answer relevancy | Context precision | Context recall |", "|---|---:|---:|---:|---:|"]
    for run in runs:
        scores = run["scores"]
        markdown.append("| {} | {} | {} | {} | {} |".format(run["label"], *(scores[key] for key in METRICS)))
    markdown.extend(["", "Scores are local model estimates, not proof of correctness or entailment. Any null metric or failed run is recorded; this command exits nonzero if scoring is incomplete.", ""])
    args.output.with_suffix(".md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runs": runs}, indent=2))
    if _has_scoring_failure(runs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
