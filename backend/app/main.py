"""FastAPI application: HTTP endpoints for the Guided Data Analyst.

Run locally:  uvicorn app.main:app --reload --port 8000   (from backend/)
Interactive API docs are served at http://localhost:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import service
from .config import Settings, get_settings
from .errors import AppError
from .schemas import (
    AIExplanation,
    AIRequest,
    AnalysisBundle,
    AppConfig,
    DatasetProfile,
    DatasetSummary,
    DemoDataset,
    FindingsResult,
    GroupedRequest,
    GroupedSummary,
    Preview,
    ScatterData,
    ScatterRequest,
    SheetList,
    TimeSeries,
    TimeSeriesRequest,
)
from .store import SessionStore

logger = logging.getLogger("guided_data_analyst")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = SessionStore(settings)
    app = FastAPI(
        title="Guided Data Analyst API",
        version="1.0.0",
        description="Upload a CSV/XLSX dataset, profile it, explore it, get evidence-backed findings and export a report.",
    )
    app.state.settings = settings
    app.state.store = store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def guard_and_headers(request: Request, call_next):
        # Reject oversized uploads before the body is read, when the size is declared.
        length = request.headers.get("content-length")
        if request.method == "POST" and length and length.isdigit():
            if int(length) > settings.max_upload_bytes + 1024 * 1024:  # allow for multipart overhead
                err = AppError(413, "file_too_large", f"The file is larger than the {settings.max_upload_mb} MB limit.")
                return JSONResponse(err.to_dict(), status_code=err.status)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(exc.to_dict(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e.get("loc", [])) for e in exc.errors()]
        err = AppError(422, "invalid_request", "The request was missing or had invalid fields.", {"fields": fields})
        return JSONResponse(err.to_dict(), status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_handler(_: Request, exc: Exception) -> JSONResponse:
        # Log the exception type only: messages can contain cell values.
        logger.error("Unexpected error: %s", type(exc).__name__)
        err = AppError(
            500, "internal_error", "Something went wrong while processing the data. Please try again or use a different file."
        )
        return JSONResponse(err.to_dict(), status_code=500)

    async def read_upload(file: UploadFile) -> bytes:
        data = await file.read(settings.max_upload_bytes + 1)
        await file.close()
        if len(data) > settings.max_upload_bytes:
            raise AppError(413, "file_too_large", f"The file is larger than the {settings.max_upload_mb} MB limit.")
        return data

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config", response_model=AppConfig)
    def config() -> AppConfig:
        return service.app_config(settings)

    @app.get("/api/demo-datasets", response_model=list[DemoDataset])
    def demos() -> list[DemoDataset]:
        return service.demo_list()

    # ---------------------------------------------------------------- upload
    @app.post("/api/files/sheets", response_model=SheetList)
    async def sheets(file: UploadFile = File(...)) -> SheetList:
        return service.sheets_for_upload(await read_upload(file), file.filename, settings)

    @app.post("/api/datasets", response_model=DatasetSummary, status_code=201)
    async def upload(file: UploadFile = File(...), sheet: str | None = Form(default=None, max_length=200)) -> DatasetSummary:
        data = await read_upload(file)
        return service.load_upload(store, data, file.filename, settings, sheet=sheet or None)

    @app.post("/api/demo-datasets/{key}", response_model=DatasetSummary, status_code=201)
    def load_demo(key: str) -> DatasetSummary:
        return service.load_demo(store, key, settings)

    # --------------------------------------------------------------- dataset
    @app.get("/api/datasets/{dataset_id}", response_model=DatasetSummary)
    def get_dataset(dataset_id: str) -> DatasetSummary:
        return service.summary(store, store.get(dataset_id))

    @app.delete("/api/datasets/{dataset_id}", status_code=204)
    def delete_dataset(dataset_id: str) -> Response:
        store.delete(dataset_id)
        return Response(status_code=204)

    @app.get("/api/datasets/{dataset_id}/preview", response_model=Preview)
    def get_preview(dataset_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)) -> Preview:
        return service.preview(store.get(dataset_id), offset, limit)

    @app.get("/api/datasets/{dataset_id}/profile", response_model=DatasetProfile)
    def get_profile(dataset_id: str) -> DatasetProfile:
        return service.get_profile(store.get(dataset_id))

    @app.get("/api/datasets/{dataset_id}/analysis", response_model=AnalysisBundle)
    def get_analysis(dataset_id: str) -> AnalysisBundle:
        return service.get_analysis(store.get(dataset_id))

    @app.post("/api/datasets/{dataset_id}/explore/grouped", response_model=GroupedSummary)
    def explore_grouped(dataset_id: str, body: GroupedRequest) -> GroupedSummary:
        return service.explore_grouped(store.get(dataset_id), body.category_column, body.value_column)

    @app.post("/api/datasets/{dataset_id}/explore/scatter", response_model=ScatterData)
    def explore_scatter(dataset_id: str, body: ScatterRequest) -> ScatterData:
        return service.explore_scatter(store.get(dataset_id), body.x, body.y)

    @app.post("/api/datasets/{dataset_id}/explore/timeseries", response_model=TimeSeries)
    def explore_timeseries(dataset_id: str, body: TimeSeriesRequest) -> TimeSeries:
        return service.explore_timeseries(store.get(dataset_id), body.date_column, body.value_column, body.agg, body.granularity)

    @app.get("/api/datasets/{dataset_id}/findings", response_model=FindingsResult)
    def get_findings(dataset_id: str) -> FindingsResult:
        return service.get_findings(store.get(dataset_id))

    # ---------------------------------------------------------------- report
    @app.get("/api/datasets/{dataset_id}/report.html", response_class=HTMLResponse)
    def report_html(dataset_id: str, download: bool = Query(True)) -> HTMLResponse:
        session = store.get(dataset_id)
        html = service.report_html(session)
        headers = {
            # The report is static: no scripts, no external requests.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        }
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{service.report_filename(session, "html")}"'
        return HTMLResponse(html, headers=headers)

    @app.get("/api/datasets/{dataset_id}/export/{table}.csv")
    def export_csv(dataset_id: str, table: str) -> Response:
        session = store.get(dataset_id)
        content = service.export_table(session, table)
        name = service.report_filename(session, "csv").replace("-analysis.csv", f"-{table}.csv")
        return Response(
            content="﻿" + content,  # BOM so Excel opens UTF-8 correctly
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    # -------------------------------------------------------------------- AI
    @app.post("/api/datasets/{dataset_id}/ai-explanation", response_model=AIExplanation)
    def ai_explanation(dataset_id: str, body: AIRequest) -> AIExplanation:
        return service.ai_explain(store.get(dataset_id), settings, body.consent)

    return app


app = create_app()
