import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import ValidationError
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.models.schemas import AnalysisResponse, AnalysisSummary, CallMetadata, TransactionContext
from app.models.tables import Analysis
from app.services import evidence, pipeline, retention, scenarios, workflow
from app.services.audio_io import AudioError

log = logging.getLogger("vaaniguard.api")
router = APIRouter()


def api_error(status: int, code: str, message: str, hint: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "hint": hint})


@router.get("/scenarios", response_model=list[scenarios.ScenarioSummary])
def list_scenarios():
    return scenarios.summaries()


@router.get("/scenarios/{scenario_id}/audio")
def scenario_audio(scenario_id: str):
    """Bundled (synthetic) demo audio, so the Live Monitor can play it in sync with the analysis."""
    sc = scenarios.get_scenario(scenario_id)
    if sc is None or not sc.audio_path.exists():
        raise api_error(404, "scenario_audio_missing", "No audio for this scenario.", "GET /api/scenarios lists the available ids.")
    return FileResponse(sc.audio_path, media_type="audio/wav")


@router.post("/scenarios/{scenario_id}/run", response_model=AnalysisResponse)
def run_scenario(scenario_id: str, session: Session = Depends(get_session)):
    sc = scenarios.get_scenario(scenario_id)
    if sc is None:
        raise api_error(404, "scenario_not_found", f"No scenario named '{scenario_id}'.", "GET /api/scenarios lists the available ids.")
    if not sc.audio_path.exists():
        raise api_error(500, "scenario_audio_missing", "The bundled audio for this scenario is missing.", "Run scripts/make_placeholder_audio.py or add the file to demo_audio/.")
    audio = sc.audio_path.read_bytes()
    res = pipeline.run_pipeline(audio, sc.metadata, sc.context, scenario=sc)
    res = workflow.save_new(session, res, audio, sc.id, retain=False)
    log.info("scenario_run", extra={"fields": {"analysis_id": res.id, "scenario": sc.id, "tier": res.tier, "score": res.score}})
    return res


def _parse(model, raw: str | None, name: str):
    if raw is None or raw == "":
        return None
    try:
        return model(**json.loads(raw))
    except (json.JSONDecodeError, ValidationError, TypeError):
        raise api_error(422, "invalid_json", f"'{name}' is not valid.", f"Send '{name}' as a JSON object matching the documented schema.") from None


@router.post("/analyses", response_model=AnalysisResponse)
def create_analysis(
    audio: UploadFile = File(...),
    context: str | None = Form(None),
    metadata: str | None = Form(None),
    transcript: str | None = Form(None),
    retain_audio: bool = Form(False),
    session: Session = Depends(get_session),
):
    data = audio.file.read(get_settings().max_audio_bytes + 1)
    meta = _parse(CallMetadata, metadata, "metadata") or CallMetadata(
        caller_number_masked="unknown", in_directory=False, directory_name=None, channel="unknown", started_at=datetime.now(timezone.utc)
    )
    ctx = _parse(TransactionContext, context, "context")
    try:
        res = pipeline.run_pipeline(data, meta, ctx, manual_transcript=transcript or None)
    except AudioError as e:
        raise api_error(e.status, e.code, e.message, e.hint) from None
    res = workflow.save_new(session, res, data, None, retain=retain_audio)
    log.info("analysis_created", extra={"fields": {"analysis_id": res.id, "tier": res.tier, "score": res.score}})
    return res


@router.get("/analyses", response_model=list[AnalysisSummary])
def list_analyses(limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)):
    return workflow.list_analyses(session, limit)


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str, session: Session = Depends(get_session)):
    return workflow.get_analysis(session, analysis_id)


@router.get("/analyses/{analysis_id}/audio")
def get_audio(analysis_id: str, session: Session = Depends(get_session)):
    gone = api_error(410, "audio_gone", "Audio is not retained or has expired.", "Audio is deleted after analysis unless retain_audio was set, and then only for 24 hours.")
    row = session.get(Analysis, analysis_id)
    if row is None:
        raise api_error(404, "analysis_not_found", "No analysis with this id.", "GET /api/analyses lists recent analyses.")
    if not row.audio_retained or row.audio_expires_at is None or retention.as_utc(row.audio_expires_at) <= datetime.now(timezone.utc):
        retention.sweep_expired(session)
        raise gone
    data = retention.load_audio(analysis_id)
    if data is None:
        raise gone
    return Response(content=data, media_type="audio/wav" if data[:4] == b"RIFF" else "application/octet-stream")


@router.delete("/analyses/{analysis_id}", status_code=204)
def purge_analysis(analysis_id: str, session: Session = Depends(get_session)):
    workflow.purge(session, analysis_id)
    return Response(status_code=204)


@router.get("/analyses/{analysis_id}/report")
def get_report(analysis_id: str, format: str = Query("json", pattern="^(json|html)$"), session: Session = Depends(get_session)):
    res = workflow.get_analysis(session, analysis_id)
    report = evidence.build_report(session, res)
    if format == "html":
        return HTMLResponse(evidence.report_html(report))
    return json.loads(evidence.canonical_json(report))
