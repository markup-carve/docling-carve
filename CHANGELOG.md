# Changelog

## [0.1.0] - 2026-10-24

Docling documents can be exported to Carve through a native writer, CLI, HTTP endpoint, or MCP interface. Conversion reports losses and can produce review bundles.

### Fixes

- Native Carve parsing follows the 0.1.12 table span, wrapped attribute, and continuation marker rulings.

### Improvements

- Convert Docling documents and JSON to Carve while preserving nested lists, table spans, captions, formatting, image assets, and available provenance (#1).
- Report omitted or normalized content and provide strict refusal for conversions that cannot meet the requested fidelity (#1).
- Use CLI conversion and batching, optional extraction, HTTP and MCP interfaces, or a review bundle with source, AST, report, preview, assets, and original JSON (#1).

**Full Changelog**: https://github.com/markup-carve/docling-carve/compare/ecb7a8fed70cd909026b6890f2c0793aa58a8497...0.1.0
