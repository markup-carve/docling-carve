"""Docling JSON boundary shared by the CLI, HTTP, and MCP interfaces."""

from __future__ import annotations
import base64
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from docling_core.types.doc import DoclingDocument
from PIL import Image

from .exporter import export_docling
from .result import DoclingExport, DoclingExportError

DEFAULT_MAX_INPUT_BYTES = 64_000_000


def load_document(
    payload: str | bytes | dict[str, Any],
    *,
    asset_root: str | Path | None = None,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_image_pixels: int = 40_000_000,
    max_asset_bytes: int = 16_000_000,
) -> DoclingDocument:
    """Validate Docling JSON; external image files require an explicit asset root."""
    for name, value in (
        ("max_input_bytes", max_input_bytes),
        ("max_image_pixels", max_image_pixels),
        ("max_asset_bytes", max_asset_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(name + " must be a positive integer")
    if not isinstance(payload, (str, bytes, dict)):
        raise ValueError("Expected Docling JSON as an object, string, or bytes")
    if isinstance(payload, dict):
        size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        data = json.loads(json.dumps(payload, ensure_ascii=False))
    else:
        encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
        size = len(encoded)
        if size > max_input_bytes:
            raise ValueError("Docling JSON exceeds max_input_bytes")
        data = json.loads(encoded)
    if size > max_input_bytes:
        raise ValueError("Docling JSON exceeds max_input_bytes")
    if not isinstance(data, dict):
        raise ValueError("Expected a Docling document object")
    root = Path(asset_root).resolve(strict=True) if asset_root is not None else None
    if root is not None and not root.is_dir():
        raise ValueError("asset_root must be a directory")
    # Image references can occur on pages as well as pictures; pictures may
    # obtain their pixels by cropping a referenced page image.
    stack: list[Any] = [data]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            image = value.get("image")
            if isinstance(image, dict) and isinstance(image.get("uri"), str):
                uri = image["uri"]
                parsed = urlsplit(uri)
                if parsed.scheme == "data":
                    header, separator, content = uri.partition(",")
                    if not separator or not header.startswith("data:image/"):
                        raise ValueError("Invalid embedded image URI")
                    try:
                        raw = (
                            base64.b64decode(content, validate=True)
                            if header.endswith(";base64")
                            else unquote(content).encode("latin-1")
                        )
                    except (ValueError, UnicodeError) as error:
                        raise ValueError("Invalid embedded image encoding") from error
                    if len(raw) > max_asset_bytes:
                        raise ValueError("Embedded image exceeds max_asset_bytes")
                    with Image.open(BytesIO(raw)) as img:
                        if img.width * img.height > max_image_pixels:
                            raise ValueError("Image exceeds max_image_pixels")
                elif parsed.scheme == "file" and root is not None:
                    if parsed.netloc not in ("", "localhost"):
                        raise ValueError("Network file image references are not allowed")
                    path = Path(url2pathname(parsed.path)).resolve(strict=True)
                    if not path.is_relative_to(root) or not path.is_file():
                        raise ValueError("Image path escapes asset_root")
                    if path.stat().st_size > max_asset_bytes:
                        raise ValueError("Image file exceeds max_asset_bytes")
                    with Image.open(path) as img:
                        if img.width * img.height > max_image_pixels:
                            raise ValueError("Image exceeds max_image_pixels")
                    raw = path.read_bytes()
                    image["uri"] = (
                        "data:image/"
                        + (img.format or "png").lower()
                        + ";base64,"
                        + base64.b64encode(raw).decode("ascii")
                    )
                else:
                    raise ValueError(
                        "External image references require a contained asset_root; remote images are not fetched"
                    )
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return DoclingDocument.model_validate(data)


def export_json(
    payload: str | bytes | dict[str, Any],
    *,
    asset_root: str | Path | None = None,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_image_pixels: int = 40_000_000,
    **options: Any,
) -> DoclingExport:
    try:
        document = load_document(
            payload,
            asset_root=asset_root,
            max_input_bytes=max_input_bytes,
            max_image_pixels=max_image_pixels,
            max_asset_bytes=options.get("max_asset_bytes", 16_000_000),
        )
        try:
            result = export_docling(document, **options)
        except DoclingExportError as error:
            error.result.document = (
                json.loads(json.dumps(payload))
                if isinstance(payload, dict)
                else json.loads(payload)
            )
            raise
        result.document = (
            json.loads(json.dumps(payload)) if isinstance(payload, dict) else json.loads(payload)
        )
        return result
    except RecursionError as error:
        raise ValueError("Document nesting exceeds the supported traversal depth") from error
