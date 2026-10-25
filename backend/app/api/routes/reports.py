from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.db.models import User
from app.services.audit import record_audit
from app.services.auth import get_current_user
from app.services.rate_limit import enforce_rate_limit
from app.services.reports import generate_grounded_report

router = APIRouter(prefix="/reports", tags=["Reports"])


class ReportRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=180)


@router.post("/generate")
def generate_report(
    payload: ReportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    enforce_rate_limit(request, scope="report", limit=10)
    try:
        report = generate_grounded_report(
            db,
            user_id=user.id,
            is_admin=user.role == "admin",
            question=payload.question,
            title=payload.title,
        )
        record_audit(
            db,
            actor_id=user.id,
            action="report.generated",
            resource_type="report",
            details={
                "source_document_ids": [
                    source.get("document_id") for source in report["sources"]
                ],
                "verification_status": report["verification"].get("status"),
            },
        )
        return report
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        record_audit(
            db,
            actor_id=user.id,
            action="report.failed",
            resource_type="report",
            details={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=502,
            detail="The report could not pass evidence validation.",
        ) from exc
