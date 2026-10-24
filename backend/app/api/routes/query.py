from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.db.models import User
from app.services.auth import get_current_user
from app.services.generation import answer_question
from app.services.audit import record_audit
from app.services.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/query", tags=["RAG Query"])


@router.post("/")
def query_documents(
    request: Request,
    question: Annotated[str, Form(max_length=4000)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    enforce_rate_limit(request, scope="query", limit=30)
    try:
        result = answer_question(
            db,
            user_id=user.id,
            is_admin=user.role == "admin",
            question=question,
        )
        record_audit(
            db,
            actor_id=user.id,
            action="query.completed",
            resource_type="query",
            details={
                "question_length": len(question),
                "retrieved_count": result.get("retrieved_count", 0),
                "model": result.get("model"),
            },
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        record_audit(
            db,
            actor_id=user.id,
            action="query.failed",
            resource_type="query",
            details={"error_type": type(exc).__name__},
        )
        # Provider exception text can contain upstream payloads or deployment
        # details; keep the response actionable but non-sensitive.
        raise HTTPException(
            status_code=502,
            detail="The answer service could not complete this request.",
        ) from exc
    except Exception as exc:
        record_audit(
            db,
            actor_id=user.id,
            action="query.failed",
            resource_type="query",
            details={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=500,
            detail="Question answering failed.",
        ) from exc
