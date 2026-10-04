"""Optional HTTP adapter with bounded request bodies and embedded asset results."""

from __future__ import annotations
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from .capabilities import capabilities
from .schema import report_schema
from ._native import __version__
from .json_api import export_json
from .result import DoclingExportError

_ALLOWED_OPTIONS = {
    "strict",
    "max_items",
    "max_table_cells",
    "max_total_table_cells",
    "max_diagnostics",
    "max_asset_bytes",
    "max_total_asset_bytes",
    "included_content_layers",
    "asset_prefix",
}


def create_app(*, max_input_bytes: int = 16_000_000, token: str | None = None) -> FastAPI:
    if (
        isinstance(max_input_bytes, bool)
        or not isinstance(max_input_bytes, int)
        or max_input_bytes < 1
    ):
        raise ValueError("max_input_bytes must be positive")
    secret = token if token is not None else os.environ.get("DOCLING_CARVE_TOKEN")
    app = FastAPI(title="docling-carve", version=__version__)

    def authorize(request: Request) -> None:
        actual = request.headers.get("authorization", "")
        if secret and not hmac.compare_digest(actual.encode(), ("Bearer " + secret).encode()):
            raise HTTPException(
                status_code=401,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def body(request: Request) -> bytes:
        authorize(request)
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > max_input_bytes:
                raise HTTPException(status_code=413, detail="Request exceeds max_input_bytes")
        return bytes(chunks)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/v1/capabilities")
    def describe(request: Request) -> dict:
        authorize(request)
        return capabilities()

    @app.get("/v1/schema")
    def schema(request: Request) -> dict:
        authorize(request)
        return report_schema()

    @app.post(
        "/v1/convert",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["document"],
                            "properties": {
                                "document": {"type": "object"},
                                "options": {"type": "object"},
                            },
                        }
                    }
                },
            }
        },
    )
    async def convert(request: Request) -> dict:
        raw = await body(request)
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict) or "document" not in envelope:
                raise ValueError("Expected an object containing document and optional options")
            if set(envelope) - {"document", "options"}:
                raise ValueError("Unknown request fields")
            options = envelope.get("options", {})
            if not isinstance(options, dict) or set(options) - _ALLOWED_OPTIONS:
                raise ValueError("Unsupported conversion options")
            if "strict" in options and not isinstance(options["strict"], bool):
                raise ValueError("strict must be boolean")
            result = await run_in_threadpool(
                export_json, envelope["document"], max_input_bytes=max_input_bytes, **options
            )
            return result.to_dict(include_assets=True)
        except DoclingExportError as error:
            raise HTTPException(
                status_code=422,
                detail={"error": str(error), "report": error.result.to_dict(include_assets=True)},
            ) from error
        except (ValueError, OSError, RecursionError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/v1/extract")
    async def extract(
        request: Request,
        filename: str = Query(..., min_length=1, max_length=255),
        strict: bool = False,
        pdf_pipeline: Literal["standard", "native"] = "standard",
        ocr: bool = True,
        max_pages: int = Query(1000, ge=1, le=1000),
    ) -> dict:
        raw = await body(request)
        name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if name in ("", ".", "..") or "\x00" in name:
            raise HTTPException(status_code=400, detail="Invalid upload filename")
        try:
            from .extraction import convert_document

            with tempfile.TemporaryDirectory(prefix="docling-carve-upload-") as directory:
                path = Path(directory) / name
                path.write_bytes(raw)
                result = await run_in_threadpool(
                    convert_document,
                    path,
                    strict=strict,
                    pdf_pipeline=pdf_pipeline,
                    ocr=ocr,
                    max_pages=max_pages,
                    max_input_bytes=max_input_bytes,
                )
            return result.to_dict(include_assets=True)
        except ImportError as error:
            raise HTTPException(
                status_code=503, detail="Install docling-carve[extract] to enable extraction"
            ) from error
        except DoclingExportError as error:
            raise HTTPException(
                status_code=422,
                detail={"error": str(error), "report": error.result.to_dict(include_assets=True)},
            ) from error
        except (ValueError, OSError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return app
