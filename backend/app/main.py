import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import health
from app.config import get_settings
from app.db import init_db
from app.logging_setup import request_id_var, setup_logging

log = logging.getLogger("vaaniguard")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    log.info("startup")
    yield


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


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    log.error("unhandled_error", extra={"fields": {"type": type(exc).__name__}})
    return _error(500, "internal_error", "Something went wrong.", "Retry; the request id is in the response headers.")


app.include_router(health.router, prefix="/api")
