"""Optional MCP adapter for JSON conversion and contained file extraction."""

from pathlib import Path
from typing import Any, Annotated
import json
from mcp.types import CallToolResult, TextContent
from mcp.server.mcpserver.exceptions import ToolError
from .result import DoclingExportError
from mcp.server.mcpserver import MCPServer
from .capabilities import capabilities
from .schema import report_schema
from .json_api import export_json


def create_server(*, root: str | Path | None = None) -> MCPServer:
    allowed_root = Path(root).resolve(strict=True) if root is not None else None
    if allowed_root is not None and not allowed_root.is_dir():
        raise ValueError("MCP root must be a directory")
    server = MCPServer("docling-carve")

    def converted(call) -> CallToolResult:
        try:
            report = call().to_dict(include_assets=True)
            refused = False
        except DoclingExportError as error:
            report = error.result.to_dict(include_assets=True)
            refused = True
        except (ValueError, OSError, ImportError) as error:
            raise ToolError(str(error)) from error
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(report, ensure_ascii=False))],
            structured_content=report,
            is_error=refused,
        )

    @server.tool()
    def docling_to_carve(
        document: dict[str, Any], strict: bool = False, max_diagnostics: int = 1000
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        """Convert a Docling JSON document, returning source, reports, and embedded assets."""
        return converted(
            lambda: export_json(
                document, strict=strict, max_diagnostics=max_diagnostics, max_input_bytes=16_000_000
            )
        )

    @server.tool()
    def docling_carve_capabilities() -> dict[str, Any]:
        """Return adapter versions, output types, and installed interfaces."""
        result = capabilities()
        result["filesystem_extraction_enabled"] = allowed_root is not None
        return result

    @server.resource("docling-carve://schema/report-v1")
    def schema() -> str:
        """Return the JSON schema for export reports."""
        import json

        return json.dumps(report_schema())

    @server.tool()
    def docling_extract(
        path: str, strict: bool = False, pdf_pipeline: str = "standard", ocr: bool = True
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        """Extract a local document contained in the root passed when starting this server."""
        if allowed_root is None:
            raise ToolError("Start docling-carve mcp with --root to enable file extraction")
        try:
            source = (allowed_root / path).resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ToolError(
                "Extraction path escapes the configured root or is not a file"
            ) from error
        if not source.is_relative_to(allowed_root) or not source.is_file():
            raise ToolError("Extraction path escapes the configured root or is not a file")
        from .extraction import convert_document

        return converted(
            lambda: convert_document(
                source,
                strict=strict,
                pdf_pipeline=pdf_pipeline,
                ocr=ocr,
                max_input_bytes=16_000_000,
            )
        )

    return server
