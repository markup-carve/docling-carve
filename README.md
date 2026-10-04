# docling-carve

Convert Docling documents to Carve with provenance, image assets, and diagnostics for content that needs review. Use the Python API, command line, HTTP, or MCP interface. All interfaces share the same exporter and report contract.

The package owns its native wrapper over `carve-lang` 0.1.7. It does not require `carve-py` or an unreleased Python binding API. Python 3.10 or newer is required.

## Installation

The first release is being prepared. Until wheels are published, build from this repository with Rust and Python installed:

```sh
python -m venv .venv
. .venv/bin/activate
pip install maturin
maturin develop --release
```

After publication, install `docling-carve`. The core dependency is `docling-core`; the full extraction pipeline is optional. Extras are `extract`, `http`, and `mcp`. They can be combined, for example `docling-carve[http,extract]`.

## Python

```python
from docling_core.types.doc import DoclingDocument, DocItemLabel
from docling_carve import export_docling

doc = DoclingDocument(name="report")
doc.add_heading("Report", level=1)
doc.add_text(label=DocItemLabel.PARAGRAPH, text="Reviewed content.")
result = export_docling(doc)
print(result.value)
result.write_bundle("report-bundle")
```

`export_json(payload)` accepts a Docling JSON object, string, or bytes. `CarveDocSerializer` and `CarveSerializerProvider` implement Docling's serializer interfaces. See [the API guide](docs/api.md).

## Command line

```sh
docling-carve convert document.json -o document.crv --report report.json
docling-carve convert document.json --bundle report-bundle
docling-carve batch incoming --output-dir converted --keep-going
docling-carve convert report.pdf --extract --bundle report-bundle
docling-carve convert report.pdf --extract --pdf-pipeline native --bundle native-bundle
```

Bundles contain `document.crv`, `report.json`, `ast.json`, `preview.html`, extracted PNG assets, and `docling.json`. Existing outputs are refused. `--force` replaces a managed bundle only when it contains no unrelated files. Use `--no-source-snapshot` to omit the original document.

`--strict` refuses any conversion diagnostic and exits with status 2. Other failures use status 1. `--format` selects `carve`, `report-json`, `ast-json`, or `html`. JSON reports written to stdout include base64 assets.

## HTTP and MCP

```sh
docling-carve serve --host 127.0.0.1 --port 8080
docling-carve mcp
docling-carve mcp --root ./incoming
```

HTTP accepts Docling JSON at `POST /v1/convert`, and uploaded document bytes at `POST /v1/extract` when extraction is installed. Set `DOCLING_CARVE_TOKEN` to require a bearer token. MCP runs over stdio; file extraction requires an explicit root. See [service examples](docs/services.md) for JavaScript, PHP, and MCP clients.

## Preservation limits

Reports always set `complete: false`. Conversion checks reading order, nested lists, formatting, table geometry, captions, assets, and available provenance. It cannot establish extraction accuracy, preserve visual layout, or verify downstream rendering. Unsupported roles and normalizations produce diagnostics. The original Docling snapshot retains information outside the Carve mapping.

Body content is exported by default. Other layers must be selected explicitly. Image files from JSON require a contained `asset_root`; remote image references are rejected. Resource limits cover input bytes, document items, table cells, image pixels, asset bytes, and retained diagnostics.

See [mapping and compatibility](docs/compatibility.md), [report schema](python/docling_carve/schemas/report-v1.json), and [development and release](docs/development.md).
