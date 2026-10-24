from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.db.models import QueryFeedback, User
from app.schemas import FeedbackRequest
from app.services.audit import record_audit
from app.services.auth import get_current_user
from app.services.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("", status_code=201)
def submit_feedback(
    payload: FeedbackRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    enforce_rate_limit(request, scope="feedback", limit=30)
    entry = QueryFeedback(
        user_id=user.id,
        question=payload.question,
        answer=payload.answer,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(entry)
    try:
        db.commit()
        db.refresh(entry)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Feedback could not be saved."
        ) from exc
    record_audit(
        db,
        actor_id=user.id,
        action="feedback.submitted",
        resource_type="query_feedback",
        resource_id=str(entry.id),
        details={"rating": entry.rating, "comment_provided": bool(entry.comment)},
    )
    return {"id": str(entry.id), "status": "received"}
