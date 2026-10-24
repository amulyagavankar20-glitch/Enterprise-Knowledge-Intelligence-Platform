"""Fixed enterprise RAG evaluation against the local database.

The expected-fact checks are approximate lexical checks. They do not establish
semantic correctness, citation entailment, or factual faithfulness.
Optional model-judge scores are estimates and are not independent proof.
"""

import argparse
import json
import math
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.db.database import SessionLocal
from app.services.generation import ABSTENTION, generate_answer
from app.services.evaluation_judge import judge_rag_answer
from app.services.rag import RERANKER_SCORE_THRESHOLD, retrieve_context


USER_ID = UUID(os.getenv("RAG_EVAL_USER_ID", "af355322-852a-4753-857c-883d78d1999d"))
TOP_K = 5


def normalize_fact(value: str) -> str:
    """Normalize punctuation and spacing for approximate phrase checks."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def answer_looks_like_abstention(answer: str) -> bool:
    return bool(re.search(
        r"\b(?:cannot|can't|could not|couldn't|unable to|not present|"
        r"does not include|doesn't include|does not contain|doesn't contain|"
        r"does not provide|doesn't provide|does not identify|doesn't identify|"
        r"not listed|not provided|not available|insufficient evidence|"
        r"no (?:relevant )?(?:information|evidence|record|mention|details))\b",
        answer,
        flags=re.IGNORECASE,
    ))


def fact_match_count(text: str, facts: list[str]) -> int:
    normalized_text = normalize_fact(text)
    return sum(normalize_fact(fact) in normalized_text for fact in facts)


def fact_coverage(text: str, facts: list[str]) -> float | None:
    if not facts:
        return None
    return fact_match_count(text, facts) / len(facts)


TEST_CASES: list[dict[str, Any]] = [
    # HR policies: direct, paraphrased, and low-keyword-overlap questions.
    {"question": "How many annual paid leave days do full-time employees receive?", "facts": ["18 days"], "source": "hr_policies.txt"},
    {"question": "Can unused vacation time roll into next year? How much?", "facts": ["five", "days"], "source": "hr_policies.txt"},
    {"question": "How early should a normal leave request be submitted?", "facts": ["three working days"], "source": "hr_policies.txt"},
    {"question": "Who approves an employee's leave request?", "facts": ["reporting manager"], "source": "hr_policies.txt"},
    {"question": "What are the standard office hours during the work week?", "facts": ["9:30 AM", "6:00 PM"], "source": "hr_policies.txt"},
    {"question": "How many days each week can an employee work remotely with approval?", "facts": ["two days"], "source": "hr_policies.txt"},
    {"question": "If someone expects to be over fifteen minutes late, who should they notify?", "facts": ["manager"], "source": "hr_policies.txt"},
    # IT: policy and paraphrase coverage.
    {"question": "What is the minimum password length?", "facts": ["12 characters"], "source": "it_security_and_support.txt"},
    {"question": "Which company systems require multi-factor authentication?", "facts": ["company email", "remote access", "administrative systems"], "source": "it_security_and_support.txt"},
    {"question": "How should a suspected account takeover be reported?", "facts": ["IT help desk", "immediately"], "source": "it_security_and_support.txt"},
    {"question": "What steps are required for a critical incident affecting essential services?", "facts": ["phone", "IT on-call team", "service desk ticket"], "source": "it_security_and_support.txt"},
    {"question": "What information belongs in an incident report?", "facts": ["affected system", "business impact", "error message"], "source": "it_security_and_support.txt"},
    {"question": "How quickly are routine support tickets acknowledged?", "facts": ["one business day"], "source": "it_security_and_support.txt"},
    # Finance and procurement.
    {"question": "How long after a purchase can an employee submit an expense claim?", "facts": ["30 calendar days"], "source": "finance_and_procurement.txt"},
    {"question": "What documentation must accompany a reimbursement request?", "facts": ["itemized receipt", "business purpose"], "source": "finance_and_procurement.txt"},
    {"question": "What approval is needed for a claim above INR 25,000?", "facts": ["department-head approval"], "source": "finance_and_procurement.txt"},
    {"question": "How long does Finance take to review a complete expense claim?", "facts": ["seven business days"], "source": "finance_and_procurement.txt"},
    {"question": "Who must approve a 40,000 rupee equipment purchase?", "facts": ["department-manager", "Finance"], "source": "finance_and_procurement.txt"},
    {"question": "What approvals apply to equipment costing INR 60,000?", "facts": ["department-manager", "Finance", "Procurement"], "source": "finance_and_procurement.txt"},
    {"question": "Can a purchase be split to stay under an approval threshold?", "facts": ["prohibited"], "source": "finance_and_procurement.txt"},
    # Software development procedures.
    {"question": "What review is required before production code can be released?", "facts": ["pull request", "one engineer", "approve"], "source": "software_development_policy.txt"},
    {"question": "Which tests need to pass before a production release?", "facts": ["unit tests", "integration tests"], "source": "software_development_policy.txt"},
    {"question": "When must a critical security finding be resolved?", "facts": ["before deployment"], "source": "software_development_policy.txt"},
    {"question": "Who authorizes a production release?", "facts": ["release owner"], "source": "software_development_policy.txt"},
    {"question": "What must happen after an emergency code change?", "facts": ["documented", "two business days"], "source": "software_development_policy.txt"},
    # Employee directory multi-fact answers.
    {"question": "Where does Rahul Mehta work, and what is his role?", "facts": ["NOVA TECH SOLUTIONS", "IT Support Engineer", "Pune"], "source": "employee_directory.txt"},
    {"question": "Which department and city is Aditi Sharma associated with?", "facts": ["Human Resources", "Mumbai"], "source": "employee_directory.txt"},
    # Unsupported questions must abstain.
    {"question": "What is the CEO's name?", "facts": [], "source": None},
    {"question": "What is the company's annual revenue?", "facts": [], "source": None},
    {"question": "How many employees work in the Singapore office?", "facts": [], "source": None},
    {"question": "What is the CEO's personal phone number?", "facts": [], "source": None},
]


def evaluate_case(
    db, case: dict[str, Any], *, use_semantic_judge: bool = False
) -> dict[str, Any]:
    started = time.perf_counter()
    retrieved = retrieve_context(db, user_id=USER_ID, question=case["question"])
    sources = retrieved.get("sources", [])
    expected_source = case["source"]
    ranked_filenames = [source.get("filename") for source in sources]
    rank = (
        ranked_filenames.index(expected_source) + 1
        if expected_source in ranked_filenames
        else None
    )
    answerable = expected_source is not None
    # Retrieval recall is meaningful only for answerable queries. An unsupported
    # query can retrieve a related chunk and still be correctly declined.
    retrieval_success = rank is not None if answerable else None
    unsupported_retrieval_empty = not sources if not answerable else None

    answer = ABSTENTION
    actual_model = None
    generation_error = None
    if sources:
        valid_source_numbers = {
            int(source["source_number"]) for source in sources
        }
        try:
            answer, actual_model = generate_answer(
                retrieved["question"],
                retrieved["context"],
                valid_source_numbers,
            )
        except RuntimeError as exc:
            generation_error = type(exc).__name__

    expected_facts = case["facts"]
    matched_answer_facts = fact_match_count(answer, expected_facts)
    answer_fact_coverage = (
        fact_coverage(answer, expected_facts)
        if answerable and generation_error is None else None
    )
    answer_facts_complete = (
        matched_answer_facts == len(expected_facts)
        if answerable and generation_error is None else None
    )
    evidence = " ".join(source.get("content", "") for source in sources).casefold()
    evidence_fact_coverage = fact_coverage(evidence, expected_facts) if answerable else None

    cited_numbers = [
        int(number)
        for number in re.findall(r"\[Source\s+(\d+)\]", answer, re.IGNORECASE)
    ]
    valid_source_numbers = {
        int(source.get("source_number", index))
        for index, source in enumerate(sources, start=1)
    }
    citation_labels_valid = (
        all(number in valid_source_numbers for number in cited_numbers)
        if generation_error is None else None
    )
    citation_present = bool(cited_numbers) if generation_error is None else None
    if answerable or generation_error is not None:
        abstention_correct = None
    else:
        abstention_correct = answer_looks_like_abstention(answer)

    if answerable:
        checks = [
            retrieval_success,
            bool(answer_facts_complete),
            citation_labels_valid is True,
            citation_present is True,
        ]
    else:
        checks = [bool(abstention_correct)]

    rag_latency = round(time.perf_counter() - started, 4)
    semantic_judgment = None
    semantic_judge_error = None
    semantic_judge_latency = None
    semantic_pass = None
    if use_semantic_judge and generation_error is None:
        judge_started = time.perf_counter()
        try:
            semantic_judgment = judge_rag_answer(
                question=retrieved["question"],
                answer=answer,
                context=retrieved.get("context", ""),
                expected_answerable=answerable,
            )
            if answerable:
                semantic_pass = all(
                    semantic_judgment[field]
                    for field in (
                        "answer_addresses_question",
                        "claims_supported_by_evidence",
                        "citation_entailment",
                    )
                )
            else:
                semantic_pass = semantic_judgment["abstention_correct"]
        except RuntimeError as exc:
            semantic_judge_error = type(exc).__name__
        semantic_judge_latency = round(time.perf_counter() - judge_started, 4)

    return {
        "question": case["question"],
        "expected_facts": expected_facts,
        "expected_source_label": expected_source,
        "source_rank": rank,
        "retrieved_count": len(sources),
        "answer": answer,
        "model": actual_model,
        "generation_error": generation_error,
        "retrieval_success_at_k": retrieval_success,
        "unsupported_retrieval_empty": unsupported_retrieval_empty,
        "source_scores": [
            {
                "filename": source.get("filename"),
                "reranker_score": source.get("reranker_score"),
            }
            for source in sources
        ],
        "answer_expected_facts_matched_count": (
            matched_answer_facts if answerable and generation_error is None else None
        ),
        "answer_expected_facts_total": len(expected_facts) if answerable else None,
        "answer_expected_fact_coverage_approximate": answer_fact_coverage,
        "answer_expected_facts_complete_approximate": answer_facts_complete,
        "evidence_expected_facts_approximate": evidence_fact_coverage,
        "citation_labels_valid": citation_labels_valid,
        "citation_present": citation_present,
        "abstention_correct": abstention_correct,
        "semantic_judgment": semantic_judgment,
        "semantic_judge_error": semantic_judge_error,
        "semantic_pass_approximate": semantic_pass,
        "semantic_judge_latency_seconds": semantic_judge_latency,
        "latency_seconds": rag_latency,
        "passed": all(checks),
    }


def rate(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return round(sum(bool(value) for value in values) / len(values), 4)


def evaluate_thresholds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observed_scores = sorted({
        float(source["reranker_score"])
        for row in rows
        for source in row.get("source_scores", [])
        if source.get("reranker_score") is not None
    })
    candidates = {RERANKER_SCORE_THRESHOLD}
    candidates.update(
        threshold for threshold in (0.01, 0.05, 0.1, 0.2, 0.5, 1.0)
        if threshold >= RERANKER_SCORE_THRESHOLD
    )
    if observed_scores:
        quantile_indexes = {
            0,
            len(observed_scores) // 4,
            len(observed_scores) // 2,
            3 * len(observed_scores) // 4,
            len(observed_scores) - 1,
        }
        candidates.update(
            observed_scores[index]
            for index in quantile_indexes
            if observed_scores[index] >= RERANKER_SCORE_THRESHOLD
        )

    answerable = [row for row in rows if row.get("expected_source_label")]
    unsupported = [row for row in rows if row.get("expected_source_label") is None]
    output = []
    for threshold in sorted(candidates):
        accepted = {
            row["question"]: [
                source for source in row.get("source_scores", [])
                if source.get("reranker_score") is not None
                and float(source["reranker_score"]) >= threshold
            ]
            for row in rows
        }
        relevant_hits = [
            any(source.get("filename") == row["expected_source_label"]
                for source in accepted[row["question"]])
            for row in answerable
        ]
        unsupported_abstentions = [
            not accepted[row["question"]] for row in unsupported
        ]
        empty_retrieval_rate = (
            round(sum(unsupported_abstentions) / len(unsupported_abstentions), 4)
            if unsupported_abstentions else None
        )
        output.append({
            "threshold": round(threshold, 6),
            "answerable_recall_at_5": round(
                sum(relevant_hits) / len(relevant_hits), 4
            ) if relevant_hits else None,
            "unsupported_empty_retrieval_rate": empty_retrieval_rate,
            "unsupported_false_retrieval_rate": (
                round(1 - empty_retrieval_rate, 4)
                if empty_retrieval_rate is not None else None
            ),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--semantic-judge",
        action="store_true",
        help="Use the configured generation provider to estimate answer and citation support.",
    )
    args = parser.parse_args()
    rows = []
    with SessionLocal() as db:
        for case in TEST_CASES:
            try:
                row = evaluate_case(
                    db, case, use_semantic_judge=args.semantic_judge
                )
            except Exception as exc:
                db.rollback()
                row = {
                    "question": case["question"],
                    "expected_facts": case["facts"],
                    "expected_source_label": case["source"],
                    "error": type(exc).__name__,
                    "passed": False,
                }
            rows.append(row)

    answerable_rows = [row for row in rows if row.get("expected_source_label")]
    reciprocal_ranks = [
        1 / row["source_rank"] if row.get("source_rank") else 0
        for row in answerable_rows
    ]
    ndcg_scores = [
        1 / math.log2(row["source_rank"] + 1)
        if row.get("source_rank") else 0
        for row in answerable_rows
    ]
    unsupported_rows = [row for row in rows if row.get("expected_source_label") is None]
    semantic_answerable_rows = [
        row for row in answerable_rows if row.get("semantic_judgment")
    ]
    semantic_unsupported_rows = [
        row for row in unsupported_rows if row.get("semantic_judgment")
    ]
    citation_rows = [
        row for row in rows
        if row.get("model") is not None and row.get("citation_labels_valid") is not None
    ]
    metrics = {
        "case_count": len(rows),
        "overall_pass_rate": rate(rows, "passed"),
        "retrieval_success_recall_at_5": rate(
            answerable_rows, "retrieval_success_at_k"
        ),
        "mrr_by_expected_source_document": round(
            sum(reciprocal_ranks) / len(reciprocal_ranks), 4
        ) if reciprocal_ranks else None,
        "ndcg_at_5_by_expected_source_document": round(
            sum(ndcg_scores) / len(ndcg_scores), 4
        ) if ndcg_scores else None,
        "unsupported_abstention_correctness": rate(
            unsupported_rows, "abstention_correct"
        ),
        "answer_expected_fact_accuracy_approximate": rate(
            answerable_rows, "answer_expected_facts_complete_approximate"
        ),
        "answer_expected_fact_coverage_approximate": round(
            sum(row.get("answer_expected_facts_matched_count", 0) for row in answerable_rows)
            / sum(row.get("answer_expected_facts_total", 0) for row in answerable_rows), 4
        ) if sum(row.get("answer_expected_facts_total", 0) for row in answerable_rows) else None,
        "unsupported_retrieval_empty_rate": rate(
            unsupported_rows, "unsupported_retrieval_empty"
        ),
        "semantic_judge_scored_cases": sum(
            row.get("semantic_judgment") is not None for row in rows
        ),
        "semantic_judge_error_count": sum(
            bool(row.get("semantic_judge_error")) for row in rows
        ),
        "semantic_answer_addresses_question": round(
            sum(row["semantic_judgment"]["answer_addresses_question"] for row in semantic_answerable_rows)
            / len(semantic_answerable_rows), 4
        ) if semantic_answerable_rows else None,
        "semantic_claims_supported_by_evidence": round(
            sum(row["semantic_judgment"]["claims_supported_by_evidence"] for row in semantic_answerable_rows)
            / len(semantic_answerable_rows), 4
        ) if semantic_answerable_rows else None,
        "semantic_citation_entailment_estimate": round(
            sum(row["semantic_judgment"]["citation_entailment"] for row in semantic_answerable_rows)
            / len(semantic_answerable_rows), 4
        ) if semantic_answerable_rows else None,
        "semantic_unsupported_abstention_estimate": round(
            sum(row["semantic_judgment"]["abstention_correct"] for row in semantic_unsupported_rows)
            / len(semantic_unsupported_rows), 4
        ) if semantic_unsupported_rows else None,
        "semantic_pass_rate_approximate": rate(rows, "semantic_pass_approximate"),
        "evidence_expected_fact_coverage_approximate": rate(
            answerable_rows, "evidence_expected_facts_approximate"
        ),
        "citation_label_validity": rate(citation_rows, "citation_labels_valid"),
        "citation_scored_answers": len(citation_rows),
        "citation_presence_answerable": rate(answerable_rows, "citation_present"),
        "abstention_correctness": rate(rows, "abstention_correct"),
        "unsupported_abstention_cases_scored": sum(
            row.get("abstention_correct") is not None for row in unsupported_rows
        ),
        "average_latency_seconds": round(
            sum(row.get("latency_seconds", 0) for row in rows)
            / len(rows), 4
        ) if rows else None,
        "p95_latency_seconds": round(
            sorted(row.get("latency_seconds", 0) for row in rows)[
                min(len(rows) - 1, int(0.95 * len(rows)))
            ], 4
        ) if rows else None,
    }
    output = {
        "evaluation": "fixed enterprise RAG evaluation with approximate lexical checks",
        "execution_status": (
            "completed_with_evaluation_errors"
            if any(row.get("generation_error") or row.get("semantic_judge_error") for row in rows)
            else "completed"
        ),
        "case_count": len(rows),
        "generation_error_count": sum(
            bool(row.get("generation_error")) for row in rows
        ),
        "semantic_judge": {
            "enabled": args.semantic_judge,
            "provider": os.getenv("GENERATION_PROVIDER", "ollama"),
            "model": (
                os.getenv("EVAL_JUDGE_MODEL")
                or (
                    os.getenv("OPENROUTER_MODEL", "openrouter/free")
                    if os.getenv("GENERATION_PROVIDER", "ollama").strip().lower() == "openrouter"
                    else os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
                )
            ) if args.semantic_judge else None,
            "interpretation": (
                "Model-assisted judgments are estimates; the default judge uses the same provider/model as generation and is not independent proof."
            ),
        },
        "interpretation": (
            "Lexical expected-fact checks are approximate; results do not prove "
            "semantic correctness, factual faithfulness, or citation entailment."
        ),
        "retrieval_labels": "expected source document filename; chunk labels are not stored in the fixtures",
        "top_k": TOP_K,
        "reranker_score_threshold": RERANKER_SCORE_THRESHOLD,
        "metrics": metrics,
        "threshold_sweep": evaluate_thresholds(rows),
        "threshold_sweep_scope": (
            "Thresholds at or above the configured threshold, applied to candidates "
            "retained at the configured threshold; lower-threshold scores were not retrieved."
        ),
        "results": rows,
    }
    evaluation_dir = PROJECT_ROOT / "reports" / "evaluation"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    output_path = evaluation_dir / "enterprise_rag_evaluation_results.json"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    report = [
        "# Enterprise RAG Evaluation",
        "",
        f"- Cases: {metrics['case_count']}",
        f"- Overall pass rate: {metrics['overall_pass_rate']}",
        f"- Retrieval success / Recall@5: {metrics['retrieval_success_recall_at_5']}",
        f"- MRR by expected source document: {metrics['mrr_by_expected_source_document']}",
        f"- nDCG@5 by expected source document: {metrics['ndcg_at_5_by_expected_source_document']}",
        f"- Expected-fact answer accuracy (approximate): {metrics['answer_expected_fact_accuracy_approximate']}",
        f"- Per-fact answer coverage (approximate): {metrics['answer_expected_fact_coverage_approximate']}",
        f"- Evidence expected-fact coverage (approximate): {metrics['evidence_expected_fact_coverage_approximate']}",
        f"- Citation label validity: {metrics['citation_label_validity']}",
        f"- Citation-scored answers: {metrics['citation_scored_answers']}",
        f"- Citation presence on answerable cases: {metrics['citation_presence_answerable']}",
        f"- Abstention correctness: {metrics['abstention_correctness']}",
        f"- Unsupported abstention cases scored: {metrics['unsupported_abstention_cases_scored']}",
        f"- Unsupported queries with empty retrieval: {metrics['unsupported_retrieval_empty_rate']}",
        f"- Model-judge coverage / errors: {metrics['semantic_judge_scored_cases']} / {metrics['semantic_judge_error_count']}",
        f"- Model-estimated answer support / citation entailment: {metrics['semantic_claims_supported_by_evidence']} / {metrics['semantic_citation_entailment_estimate']}",
        f"- Average / p95 latency (seconds): {metrics['average_latency_seconds']} / {metrics['p95_latency_seconds']}",
        "",
        "## Reranker threshold sweep",
        "",
        "| Threshold | Answerable Recall@5 | Unsupported empty retrieval | Unsupported false retrieval |",
        "|---:|---:|---:|---:|",
    ]
    report.extend(
        f"| {item['threshold']} | {item['answerable_recall_at_5']} | "
        f"{item['unsupported_empty_retrieval_rate']} | "
        f"{item['unsupported_false_retrieval_rate']} |"
        for item in output["threshold_sweep"]
    )
    report.extend([
        "",
        "Phrase checks are approximate and do not prove semantic correctness or faithfulness. Citation number validity only confirms that a label maps to a returned source; it does not prove the source entails the claim. Retrieval labels are document filenames because deterministic chunk-level labels are not present in the current fixture/index format.",
        "The optional model judge uses the configured generation provider (the same model by default), so its support and entailment estimates are useful signals but are not independent or conclusive evidence.",
        "",
        "Machine-readable detail: `reports/evaluation/enterprise_rag_evaluation_results.json`.",
    ])
    (evaluation_dir / "enterprise_rag_evaluation_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
