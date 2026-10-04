"""Optional Docling extraction pipeline; JSON conversion needs no models."""

from __future__ import annotations
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import threading
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen

from .exporter import export_docling
from .result import DoclingExport, DoclingExportError

_converter_lock = threading.Lock()


@lru_cache(maxsize=4)
def _converter(pdf_pipeline: str, ocr: bool) -> Any:
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except ImportError as error:
        raise ImportError(
            "Install docling-carve[extract] to extract PDF, Office, HTML, or image inputs"
        ) from error
    if pdf_pipeline == "native":
        from docling.document_converter import NativePdfFormatOption
        from docling.datamodel.pipeline_options import NativePdfPipelineOptions

        pdf = NativePdfFormatOption(
            pipeline_options=NativePdfPipelineOptions(generate_page_images=True)
        )
    elif pdf_pipeline == "standard":
        pdf = PdfFormatOption(
            pipeline_options=PdfPipelineOptions(
                do_ocr=ocr,
                generate_picture_images=True,
                generate_page_images=True,
                enable_remote_services=False,
                allow_external_plugins=False,
            )
        )
    else:
        raise ValueError("pdf_pipeline must be standard or native")
    return DocumentConverter(format_options={InputFormat.PDF: pdf})


def convert_document(
    source: str | Path,
    *,
    allow_url: bool = False,
    pdf_pipeline: str = "standard",
    ocr: bool = True,
    max_pages: int = 1000,
    max_input_bytes: int = 64_000_000,
    converter: Any = None,
    **options: Any,
) -> DoclingExport:
    """Extract a local file, or an explicitly allowed URL, and export its document."""
    for name, limit in (("max_pages", max_pages), ("max_input_bytes", max_input_bytes)):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(name + " must be a positive integer")
    if not isinstance(ocr, bool) or not isinstance(allow_url, bool):
        raise ValueError("ocr and allow_url must be boolean")
    if not isinstance(options.get("strict", False), bool):
        raise ValueError("strict must be boolean")
    try:
        from docling.datamodel.base_models import DocumentStream
        from docling.exceptions import ConversionError
    except ImportError as error:
        raise ImportError("Install docling-carve[extract] to use document extraction") from error
    parsed = urlsplit(str(source))
    if parsed.scheme in ("http", "https"):
        if not allow_url:
            raise ValueError("URL extraction requires allow_url=True or --allow-url")
        with urlopen(str(source), timeout=30) as response:
            payload = response.read(max_input_bytes + 1)
        name = Path(parsed.path).name or "document.pdf"
    else:
        path = Path(source)
        with path.open("rb") as stream:
            payload = stream.read(max_input_bytes + 1)
        name = path.name
    if len(payload) > max_input_bytes:
        raise ValueError("Input document exceeds max_input_bytes")
    strict = options.pop("strict", False)
    asset_dir = options.pop("asset_dir", None)
    with _converter_lock:
        pipeline = converter if converter is not None else _converter(pdf_pipeline, ocr)
        try:
            converted = pipeline.convert(
                DocumentStream(name=name, stream=BytesIO(payload)),
                raises_on_error=True,
                max_num_pages=max_pages,
                max_file_size=max_input_bytes,
            )
        except ConversionError as error:
            raise ValueError("Docling extraction failed: " + str(error)) from error
    status = getattr(converted.status, "value", str(converted.status))
    if status not in ("success", "partial_success"):
        raise ValueError("Docling extraction failed: " + status)
    result = export_docling(converted.document, strict=False, **options)
    if status == "partial_success":
        result.total_diagnostics += 1
        if len(result.diagnostics) < result.max_diagnostics:
            result.diagnostics.append(
                {
                    "code": "extraction-partial",
                    "ref": converted.document.body.self_ref,
                    "path": None,
                    "message": "Docling reported partial extraction success.",
                }
            )
    result.source["extraction_status"] = status
    if strict and result.total_diagnostics:
        raise DoclingExportError(result)
    if asset_dir is not None:
        target = Path(asset_dir)
        target.mkdir(parents=True, exist_ok=True)
        for name, content in result.assets.items():
            destination = target / name
            if destination.is_symlink():
                raise ValueError("Asset output must not replace a symlink")
            destination.write_bytes(content)
    return result
