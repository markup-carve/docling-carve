"""Discover installed interfaces without loading extraction models."""

from importlib.util import find_spec
from docling_core.types.doc import DoclingDocument
from ._native import ENGINE_VERSION, __version__


def capabilities() -> dict:
    return {
        "schema_version": "1",
        "adapter": "docling-carve",
        "version": __version__,
        "engine_version": ENGINE_VERSION,
        "docling_schema_version": DoclingDocument.model_fields["version"].default,
        "inputs": ["DoclingDocument", "Docling JSON"],
        "outputs": ["Carve", "Carve AST JSON", "report JSON", "HTML preview", "artifact bundle"],
        "interfaces": {
            "python": True,
            "cli": True,
            "extract": find_spec("docling") is not None,
            "http": find_spec("fastapi") is not None,
            "mcp": find_spec("mcp") is not None,
        },
        "complete": False,
    }
