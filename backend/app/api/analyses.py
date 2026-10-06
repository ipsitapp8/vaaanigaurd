import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.config import get_settings
from app.models.schemas import AnalysisResponse, CallMetadata, TransactionContext
from app.services import pipeline, scenarios
from app.services.audio_io import AudioError

log = logging.getLogger("vaaniguard.api")
router = APIRouter()


def api_error(status: int, code: str, message: str, hint: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "hint": hint})


@router.get("/scenarios", response_model=list[scenarios.ScenarioSummary])
def list_scenarios():
    return scenarios.summaries()


@router.post("/scenarios/{scenario_id}/run", response_model=AnalysisResponse)
def run_scenario(scenario_id: str):
    sc = scenarios.get_scenario(scenario_id)
    if sc is None:
        raise api_error(404, "scenario_not_found", f"No scenario named '{scenario_id}'.", "GET /api/scenarios lists the available ids.")
    if not sc.audio_path.exists():
        raise api_error(500, "scenario_audio_missing", "The bundled audio for this scenario is missing.", "Run scripts/make_placeholder_audio.py or add the file to demo_audio/.")
    res = pipeline.run_pipeline(sc.audio_path.read_bytes(), sc.metadata, sc.context, scenario=sc)
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
    log.info("analysis_created", extra={"fields": {"analysis_id": res.id, "tier": res.tier, "score": res.score}})
    return res
