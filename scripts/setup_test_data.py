import os
import re
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "test_data" / "enterprise_docs"

API_BASE = os.getenv("RAG_API_BASE", "http://127.0.0.1:8000")
RAG_EMAIL = os.getenv("RAG_EVAL_EMAIL", "")
RAG_PASSWORD = os.getenv("RAG_EVAL_PASSWORD", "")

DOCUMENTS = {
    "employee_directory.txt": """
NOVA TECH SOLUTIONS — EMPLOYEE DIRECTORY
Version: 1.0

Employee ID: EMP-1001
Name: Aditi Sharma
Department: Human Resources
Role: HR Manager
Location: Mumbai
Manager: Chief Operating Officer

Employee ID: EMP-1002
Name: Rahul Mehta
Department: Information Technology
Role: IT Support Engineer
Location: Pune
Manager: IT Manager

Employee ID: EMP-1003
Name: Priya Nair
Department: Finance
Role: Financial Analyst
Location: Mumbai
Manager: Finance Director

Employee ID: EMP-1004
Name: Arjun Patel
Department: Information Technology
Role: Senior Software Engineer
Location: Bengaluru
Manager: Engineering Manager

Employee ID: EMP-1005
Name: Sneha Iyer
Department: Marketing
Role: Marketing Specialist
Location: Hyderabad
Manager: Marketing Director
""",
    "hr_policies.txt": """
NOVA TECH SOLUTIONS — HR POLICIES
Version: 1.0
Effective Date: 2026-01-01

ANNUAL LEAVE POLICY — HR-POL-001

Full-time employees receive 18 days of annual paid leave per
calendar year. Employees joining during the year receive leave
on a prorated basis.

Employees should submit leave requests through the HR portal
at least three working days before the intended leave date.
Emergency leave should be reported to the manager as soon as
reasonably possible.

The reporting manager approves leave requests. Employees can
check their leave balances through the HR portal.

Up to five unused annual leave days may be carried forward
to the next calendar year. Additional carry-forward requires
written approval from Human Resources.

ATTENDANCE AND REMOTE WORK — HR-POL-002

Standard working hours are 9:30 AM to 6:00 PM, Monday through
Friday. Employees expecting to arrive more than 15 minutes late
should notify their manager.

Employees may work remotely up to two days per week with
manager approval. Role-specific operational requirements may
require additional office attendance.
""",
    "it_security_and_support.txt": """
NOVA TECH SOLUTIONS — IT SECURITY AND SUPPORT
Version: 1.0

PASSWORD SECURITY — IT-POL-001

Passwords must contain at least 12 characters and should not
be reused across company systems and personal accounts.

Multi-factor authentication is required for company email,
remote access, and administrative systems.

Employees must never share passwords or authentication codes.
Suspected account compromise must be reported to the IT help
desk immediately.

INCIDENT REPORTING — IT-POL-002

Support requests must be submitted through the internal
service desk portal.

Critical incidents affecting multiple employees or essential
business services must be reported immediately by phone to the
IT on-call team, followed by a service desk ticket.

Incident reports should include the affected system, time
observed, business impact, and any error message. Passwords,
private keys, and authentication codes must never be included.

Standard tickets are acknowledged within one business day.
Critical incidents receive priority handling.
""",
    "finance_and_procurement.txt": """
NOVA TECH SOLUTIONS — FINANCE AND PROCUREMENT
Version: 1.0

EXPENSE REIMBURSEMENT — FIN-POL-001

Expense claims must be submitted within 30 calendar days of
the transaction date.

Claims require an itemized receipt, business purpose,
transaction date, and expense category.

Claims above INR 25,000 require department-head approval
before reimbursement processing.

Finance reviews complete claims within seven business days.
Incomplete claims are returned for correction. Approved claims
are paid in the next scheduled reimbursement cycle.

EQUIPMENT PROCUREMENT — OPS-POL-001

Equipment purchases costing up to INR 10,000 require approval
from the employee's department manager.

Purchases above INR 10,000 and up to INR 50,000 require
department-manager and Finance approval.

Purchases above INR 50,000 require department-manager,
Finance, and Procurement approval.

Every purchase requires a business justification and an
appropriate cost center. Splitting purchases to avoid approval
thresholds is prohibited.
""",
    "software_development_policy.txt": """
NOVA TECH SOLUTIONS — SOFTWARE DEVELOPMENT PROCEDURES
Version: 1.0

CODE REVIEW AND RELEASE — ENG-PROC-001

All production code changes must be submitted through a
pull request. At least one engineer other than the author
must review and approve the change.

Automated unit tests and applicable integration tests must
pass before production release.

Critical security findings must be resolved before deployment.

Production releases require approval from the designated
release owner. Emergency changes must be documented and
reviewed retrospectively within two business days.

Developers must not commit API keys, passwords, customer data,
or private credentials to source control.
""",
}

TEST_CASES = [
    {
        "question": "How many annual paid leave days do full-time employees receive?",
        "expected": "18",
        "should_abstain": False,
    },
    {
        "question": "Where does Rahul Mehta work, and what is his role?",
        "expected": "Pune",
        "should_abstain": False,
    },
    {
        "question": "What approvals are required for equipment costing INR 40000?",
        "expected": "Finance",
        "should_abstain": False,
    },
    {
        "question": "What should employees do during a critical IT incident?",
        "expected": "IT",
        "should_abstain": False,
    },
    {
        "question": "What is the CEO's name?",
        "expected": None,
        "should_abstain": True,
    },
]


def answer_looks_like_abstention(answer):
    return bool(re.search(
        r"\b(?:cannot|can't|could not|couldn't|unable to|not present|"
        r"does not include|doesn't include|does not contain|doesn't contain|"
        r"does not provide|doesn't provide|does not identify|doesn't identify|"
        r"not listed|not provided|not available|insufficient evidence|"
        r"no (?:relevant )?(?:information|evidence|record|mention|details))\b",
        answer,
        flags=re.IGNORECASE,
    ))


def prepare_documents():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for filename, content in DOCUMENTS.items():
        path = DATA_DIR / filename
        path.write_text(content.strip() + "\n", encoding="utf-8")

    print(f"Created {len(DOCUMENTS)} documents in: {DATA_DIR}")


def authenticate(client):
    if not RAG_EMAIL or not RAG_PASSWORD:
        sys.exit("Set RAG_EVAL_EMAIL and RAG_EVAL_PASSWORD in this shell.")

    endpoint = f"{API_BASE}/api/v1/auth/token"
    response = client.post(
        endpoint,
        data={"username": RAG_EMAIL, "password": RAG_PASSWORD},
        timeout=15.0,
    )
    if response.status_code == 401 and os.getenv("RAG_EVAL_AUTO_REGISTER") == "1":
        registration = client.post(
            f"{API_BASE}/api/v1/auth/register",
            json={"email": RAG_EMAIL, "password": RAG_PASSWORD},
            timeout=15.0,
        )
        if registration.status_code not in (201, 409):
            registration.raise_for_status()
        response = client.post(
            endpoint,
            data={"username": RAG_EMAIL, "password": RAG_PASSWORD},
            timeout=15.0,
        )
    response.raise_for_status()
    return response.json()["access_token"]


def upload_documents(client, token):
    endpoint = f"{API_BASE}/api/v1/documents/upload"

    for filename in DOCUMENTS:
        path = DATA_DIR / filename

        with path.open("rb") as file_handle:
            response = client.post(
                endpoint,
                data={
                    "title": path.stem.replace("_", " ").title(),
                },
                headers={"Authorization": f"Bearer {token}"},
                files={
                    "file": (filename, file_handle, "text/plain")
                },
                timeout=120.0,
            )

        if response.is_error:
            print(f"UPLOAD FAILED: {filename} — {response.text}")
            response.raise_for_status()

        try:
            result = response.json()
        except ValueError:
            result = {"response": response.text}

        duplicate = result.get("duplicate", False)
        status = "ALREADY EXISTS" if duplicate else "UPLOADED"
        print(f"{status}: {filename}")


def run_tests(client, token):
    endpoint = f"{API_BASE}/api/v1/query/"
    results = []

    for case in TEST_CASES:
        response = client.post(
            endpoint,
            data={
                "question": case["question"],
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )
        response.raise_for_status()
        result = response.json()

        answer = result.get("answer", "")
        sources = result.get("sources", [])
        expected = case["expected"]

        if case["should_abstain"]:
            # A relevant-looking chunk may be retrieved for an unsupported
            # question; success depends on the response clearly declining it.
            passed = answer_looks_like_abstention(answer)
        else:
            passed = (
                bool(sources)
                and expected.casefold() in answer.casefold()
            )

        row = {
            "question": case["question"],
            "expected": expected or "ABSTAIN",
            "retrieved_count": result.get("retrieved_count", 0),
            "model": result.get("model"),
            "passed": passed,
            "answer": answer,
        }
        results.append(row)

        print(
            f"\n{'PASS' if passed else 'FAIL'}: {case['question']}"
        )
        print(f"Answer: {answer}")
        print(f"Retrieved sources: {row['retrieved_count']}")

    passed_count = sum(row["passed"] for row in results)
    total = len(results)

    import json

    evaluation_dir = PROJECT_ROOT / "reports" / "evaluation"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    output_path = evaluation_dir / "enterprise_smoke_test_results.json"
    output_path.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )

    print(f"\nFINAL RESULT: {passed_count}/{total} passed")
    print(f"Results saved to: {output_path}")


def main():
    prepare_documents()

    try:
        with httpx.Client() as client:
            # Verify the API is reachable before uploading.
            health = client.get(f"{API_BASE}/health", timeout=5.0)
            health.raise_for_status()

            token = authenticate(client)
            upload_documents(client, token)
            run_tests(client, token)

    except httpx.HTTPError as exc:
        sys.exit(
            f"API request failed: {exc}\n"
            "Ensure FastAPI is running and the test user exists."
        )


if __name__ == "__main__":
    main()
