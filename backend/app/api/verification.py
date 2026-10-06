import json

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.analyses import api_error
from app.db import get_session
from app.models.schemas import (
    AnalysisResponse,
    ReviewDecisionRequest,
    ReviewItemOut,
    VerificationComplete,
    VerificationStart,
)
from app.services import workflow

router = APIRouter()


@router.post("/analyses/{analysis_id}/verification", response_model=VerificationStart)
def start_verification(analysis_id: str, session: Session = Depends(get_session)):
    v, _ = workflow.start_verification(session, analysis_id)
    methods = json.loads(v.methods_json)
    return VerificationStart(
        verification_id=v.id,
        methods=methods,
        reason=v.reason,
        instructions={m: workflow.INSTRUCTIONS[m] for m in methods},
        outcome=v.outcome,  # type: ignore[arg-type]
    )


@router.post("/verifications/{verification_id}/complete", response_model=AnalysisResponse)
def complete_verification(verification_id: str, body: VerificationComplete, session: Session = Depends(get_session)):
    return workflow.complete_verification(session, verification_id, body.outcome, body.actor)


@router.get("/review-queue", response_model=list[ReviewItemOut])
def review_queue(include_decided: bool = Query(False), session: Session = Depends(get_session)):
    return workflow.review_queue(session, include_decided)


@router.post("/review/{review_id}/decision", response_model=AnalysisResponse)
def review_decision(review_id: str, body: ReviewDecisionRequest, session: Session = Depends(get_session)):
    if not body.note.strip():
        raise api_error(422, "note_required", "An analyst note is required.", "Explain the decision in the note field.")
    _, res = workflow.decide_review(session, review_id, body.decision, body.note)
    return res
