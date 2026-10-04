# Python API

`export_docling(document, **options)` returns a `DoclingExport`. `export_json(payload, **options)` validates and loads Docling JSON before calling the same exporter. Neither function runs OCR or downloads extraction models.

## Export options

| Option | Default | Purpose |
| --- | --- | --- |
| `strict` | `False` | Raise `DoclingExportError` when any diagnostic occurs |
| `included_content_layers` | body | Select body, furniture, background, invisible, or notes |
| `asset_prefix` | `assets` | Relative URL directory used in source and report |
| `asset_dir` | `None` | Write PNG assets after successful export |
| `max_items` | 100000 | Bound document ownership nodes |
| `max_table_cells` | 100000 | Bound each table's rectangular grid |
| `max_total_table_cells` | 1000000 | Bound all selected table grids before allocation |
| `max_diagnostics` | 1000 | Bound retained entries; total count remains available |
| `max_image_pixels` | 40000000 | Bound image dimensions |
| `max_asset_bytes` | 16000000 | Bound each generated PNG |
| `max_total_asset_bytes` | 64000000 | Bound all generated assets |

JSON loading also accepts `asset_root`, `max_input_bytes` (64000000). A local image reference must resolve inside `asset_root`. Remote images are rejected. Embedded images are checked before Docling decodes them. Document ownership depth is limited to 128 levels.

`result.value` contains source, `result.ast` the converted AST, `result.provenance` references to Docling items and available page geometry, and `result.assets` PNG bytes indexed by content hash. Provenance paths address the converted AST; they are not byte offsets in the emitted source. `result.document` is a Docling snapshot. Object input omits computed fields such as regenerated table grids; stored fields remain available. JSON input preserves its original fields before validated local images are hydrated.

`result.to_dict(include_assets=True)` embeds asset bytes as base64. `include_document=True` includes the source snapshot. The default report includes asset metadata and the converted AST. Reports follow [schema version 1](../python/docling_carve/schemas/report-v1.json).

`result.write_bundle(directory)` stages the artifacts and renames the directory into place. `overwrite=True` only replaces a managed bundle with no unrelated files. `include_document=False` omits the snapshot. `DoclingExportError.result` retains the refused report; strict mode writes no assets.

## Serializer integration

```python
from docling_carve import CarveSerializerProvider

serializer = CarveSerializerProvider(strict=True).get_serializer(document)
serialized = serializer.serialize()
print(serialized.text)
report = serializer.last_export
```

`CarveDocSerializer(doc=document, **options)` also supports `serialize(item=node)` for a subtree. Serialization spans identify exported Docling items. `get_parts()` returns one result for the requested subtree; it does not create chunk boundaries. Metadata serialization returns no source text, while the export report and snapshot retain the unsupported metadata context.

## Extraction

```python
from docling_carve.extraction import convert_document

result = convert_document("report.pdf", pdf_pipeline="native", ocr=False)
```

Install the `extract` extra. The standard PDF pipeline runs Docling's OCR/layout pipeline and may download models on first use. The native PDF pipeline uses the document's text layer and does not OCR scanned text. Office and HTML inputs use Docling's corresponding backends. Conversion is serialized within a process because converters cache pipeline state.

`allow_url=True` permits explicit HTTP(S) downloads in the Python API and CLI. HTTP uploads and MCP extraction do not accept remote URLs. `max_pages` defaults to 1000; `max_input_bytes` defaults to 64000000. A custom `converter` may be passed for configured Docling pipelines.

## CLI limits

`convert` and `batch` expose `--max-input-bytes`, `--max-items`, `--max-table-cells`, `--max-total-table-cells`, `--max-image-pixels`, `--max-asset-bytes`, `--max-total-asset-bytes`, and `--max-diagnostics`. Defaults match the API table above. Extraction also accepts `--max-pages`. `serve --max-input-bytes` sets the streamed request ceiling; other server ceilings can be configured through the Python app factory.
