"""HTTP API and static UI.

The server accepts only allow-listed Host headers (blocks DNS rebinding),
refuses cross-site writes and oversized bodies, and serves a strict CSP.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path as FilePath
from urllib.parse import urlsplit

import yt_dlp.version
from fastapi import APIRouter, FastAPI, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__, audio, preview, source
from .audio import Mode
from .config import Settings
from .errors import AppError, error_body
from .jobs import JobManager, QueueFull, State
from .urls import UrlError, canonical_url

EDITION = "local"
STATIC_DIR = FilePath(__file__).parent / "static"
JOB_ID_PATTERN = r"^[0-9a-f]{32}$"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_BODY_BYTES = 64 * 1024
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        f"img-src 'self' data: https://{preview.THUMBNAIL_HOST}",
        "connect-src 'self'",
        "media-src 'none'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), "
        "publickey-credentials-get=(self), publickey-credentials-create=(self)"
    ),
}


class AnalyzeRequest(BaseModel):
    url: str = Field(max_length=4096)


class JobRequest(BaseModel):
    url: str = Field(max_length=4096)
    mode: Mode = Mode.AAC
    split: bool = True


def _too_big(request: Request) -> bool:
    try:
        return int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES
    except ValueError:
        return True


def create_app(
    settings: Settings | None = None,
    manager: JobManager | None = None,
    prober: Callable[[str], dict] = source.probe,
) -> FastAPI:
    settings = settings or Settings.from_env()
    manager = manager or JobManager(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(title="Clickwheel", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.settings = settings
    app.state.manager = manager
    guards = []
    allow_any_host = "*" in settings.allowed_hosts

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method in WRITE_METHODS:
            # Same-origin only: the Origin's host and port must equal the Host header.
            origin = request.headers.get("origin")
            cross_site = request.headers.get("sec-fetch-site") == "cross-site"
            foreign = origin is not None and urlsplit(origin).netloc != request.headers.get("host")
            if not allow_any_host and (cross_site or foreign):
                return JSONResponse(error_body("CROSS-SITE REQUEST.", "Writes are accepted from this app only."),
                                    status_code=403, headers=SECURITY_HEADERS)
            if _too_big(request):
                return JSONResponse(error_body("TOO LARGE.", "Requests are capped at 64 KB."),
                                    status_code=413, headers=SECURITY_HEADERS)
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    @app.exception_handler(AppError)
    async def app_error(_request: Request, exc: AppError):
        return JSONResponse(error_body(exc.title, exc.message, exc.detail), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "body"
        return JSONResponse(error_body("BAD REQUEST.", f"Check the {field} field.", first.get("msg", "")),
                            status_code=422)

    def _canonical(raw: str) -> str:
        try:
            return canonical_url(raw)
        except UrlError as exc:
            raise AppError(400, exc.title, exc.message) from exc

    def _job_or_404(job_id: str):
        job = manager.get(job_id)
        if job is None:
            raise AppError(404, "NO SUCH JOB.", "It finished more than an hour ago or never existed.")
        return job

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "edition": EDITION}

    api = APIRouter(prefix="/api", dependencies=guards)

    @api.get("/info")
    def info() -> dict:
        return {
            "version": __version__,
            "yt_dlp": yt_dlp.version.__version__,
            "ffmpeg": audio.ffmpeg_version(),
            "aac_encoder": audio.aac_encoder(),
            "js_runtime": source.js_runtime(),
            "genre": settings.genre,
            "max_duration_min": settings.max_duration_min,
            "file_ttl_min": settings.file_ttl_min,
        }

    @api.post("/analyze")
    def analyze(body: AnalyzeRequest) -> dict:
        url = _canonical(body.url)
        try:
            return {"url": url, **preview.summarize(prober(url), settings)}
        except source.SourceError as exc:
            raise AppError(422, exc.title, exc.message, exc.detail) from exc

    @api.post("/jobs", status_code=202)
    def create_job(body: JobRequest) -> dict:
        url = _canonical(body.url)
        try:
            job = manager.submit(url, body.mode, body.split)
        except QueueFull as exc:
            raise AppError(429, "QUEUE FULL.", "Wait for a running job to finish.") from exc
        return job.snapshot()

    @api.get("/jobs")
    def list_jobs() -> list[dict]:
        return [job.snapshot() for job in manager.recent()]

    @api.get("/jobs/{job_id}")
    def get_job(job_id: str = Path(pattern=JOB_ID_PATTERN)) -> dict:
        return _job_or_404(job_id).snapshot()

    @api.delete("/jobs/{job_id}")
    def delete_job(job_id: str = Path(pattern=JOB_ID_PATTERN)) -> dict:
        job = manager.cancel(job_id)
        if job is None:
            raise AppError(404, "NO SUCH JOB.", "Nothing to cancel.")
        return job.snapshot()

    @api.get("/jobs/{job_id}/file")
    def job_file(job_id: str = Path(pattern=JOB_ID_PATTERN)):
        job = _job_or_404(job_id)
        if job.state is not State.DONE or job.result is None or not job.result.path.is_file():
            raise AppError(409, "NOT READY.", "The file appears when the job reaches 100%.")
        result = job.result
        media_type = "application/zip" if result.filename.endswith(".zip") else "audio/mp4"
        return FileResponse(result.path, media_type=media_type, filename=result.filename)

    app.include_router(api)
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
