import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import analyses, audit, health, verification
from app.config import get_settings
from sqlmodel import Session

from app.db import get_engine, init_db
from app.logging_setup import request_id_var, setup_logging
from app.services import model_registry, retention, workflow

log = logging.getLogger("vaaniguard")


def _sweep_once() -> None:
    try:
        with Session(get_engine()) as session:
            retention.sweep_expired(session)
    except Exception as exc:
        log.error("sweep_failed", extra={"fields": {"type": type(exc).__name__}})


async def _sweep_loop() -> None:
    """Delete expired retained audio at startup and every 10 minutes."""
    while True:
        await asyncio.to_thread(_sweep_once)
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    model_registry.start_warmup()
    sweeper = asyncio.create_task(_sweep_loop())
    log.info("startup")
    yield
    sweeper.cancel()


app = FastAPI(title="VaaniGuard", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,  # localhost only
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


def _error(status: int, code: str, message: str, hint: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "hint": hint}})


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    return _error(422, "validation_error", "Invalid request.", f"{len(exc.errors())} field(s) failed validation.")


@app.exception_handler(HTTPException)
async def http_handler(_: Request, exc: HTTPException):
    d = exc.detail
    if isinstance(d, dict) and {"code", "message", "hint"} <= d.keys():
        return _error(exc.status_code, d["code"], d["message"], d["hint"])
    return _error(exc.status_code, "http_error", str(d), "Check the request and try again.")


@app.exception_handler(workflow.NotFound)
async def not_found_handler(_: Request, exc: workflow.NotFound):
    return _error(404, "not_found", "No record with this id.", "Check the id; GET /api/analyses lists recent analyses.")


@app.exception_handler(workflow.Purged)
async def purged_handler(_: Request, exc: workflow.Purged):
    return _error(410, "purged", "This analysis was purged.", "Only a hash-only tombstone remains; see the audit log.")


@app.exception_handler(workflow.Conflict)
async def conflict_handler(_: Request, exc: workflow.Conflict):
    return _error(409, exc.code, exc.message, exc.hint)


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    log.error("unhandled_error", extra={"fields": {"type": type(exc).__name__}})
    return _error(500, "internal_error", "Something went wrong.", "Retry; the request id is in the response headers.")


app.include_router(health.router, prefix="/api")
app.include_router(analyses.router, prefix="/api")
app.include_router(verification.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
