import json
import pytest
from docling_core.types.doc import DoclingDocument, DocItemLabel, RefItem
from docling_carve import export_docling, DoclingExportError, export_json
from docling_carve import _native


def test_lists_preserve_nesting_order_start_and_provenance():
    doc = DoclingDocument(name="lists")
    group = doc.add_list_group()
    first = doc.add_list_item("one", parent=group, enumerated=True, marker="3.")
    sub = doc.add_list_group(parent=first)
    doc.add_list_item("nested", parent=sub)
    doc.add_list_item("two", parent=group, enumerated=True, marker="4.")
    result = export_docling(doc, strict=True)
    html = _native.to_html(result.value)
    assert '<ol start="3">' in html and "<ul>" in html
    assert "nested" in html and "two" in html
    assert result.ast["children"][0]["items"][0]["children"][1]["type"] == "list"
    paths = {p["path"] for p in result.provenance}
    assert "/children/0/items/0/children/1/items/0" in paths
    assert _native.to_carve(result.value) == result.value


def test_json_and_object_conversion_match_and_bundle_is_reviewable(tmp_path):
    doc = DoclingDocument(name="contract")
    doc.add_heading("Title", level=2)
    direct = export_docling(doc)
    result = export_json(doc.export_to_dict())
    assert result.to_dict() == direct.to_dict()
    destination = result.write_bundle(tmp_path / "bundle")
    assert (destination / "document.crv").read_text() == result.value
    assert json.loads((destination / "report.json").read_text())["schema_version"] == "1"
    assert (destination / "docling.json").exists()
    with pytest.raises(FileExistsError):
        result.write_bundle(destination)
    result.write_bundle(destination, overwrite=True)
    assert (destination / "preview.html").read_text() == _native.to_html(result.value)


def test_graph_cycles_limits_and_bounded_strict_reports():
    doc = DoclingDocument(name="limits")
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="furniture")
    result = export_docling(doc, max_diagnostics=0)
    assert result.total_diagnostics == 1 and result.diagnostics == []
    assert result.to_dict()["truncated"] is True
    with pytest.raises(DoclingExportError):
        export_docling(doc, strict=True, max_diagnostics=0)
    with pytest.raises(ValueError, match="max_items"):
        export_docling(doc, max_items=1)
    doc.body.children.append(RefItem(cref="#/body"))
    with pytest.raises(ValueError, match="cycle"):
        export_docling(doc)


def test_json_rejects_oversized_and_non_document_inputs():
    with pytest.raises(ValueError):
        export_json("[]")
    with pytest.raises(ValueError, match="max_input_bytes"):
        export_json("{}", max_input_bytes=1)


def test_report_schema_and_original_json_are_preserved():
    from docling_carve.schema import report_schema
    from jsonschema import Draft202012Validator

    doc = DoclingDocument(name="snapshot")
    doc.add_heading("Snapshot", level=1)
    payload = doc.export_to_dict()
    payload["custom_integration_metadata"] = {"revision": 42}
    result = export_json(payload)
    assert result.document == payload
    Draft202012Validator.check_schema(report_schema())
    Draft202012Validator(report_schema()).validate(result.to_dict(include_document=True))


def test_unknown_associated_reference_is_refused():
    doc = DoclingDocument(name="references")
    table = doc.add_table(
        data=__import__("docling_core.types.doc", fromlist=["TableData"]).TableData(
            num_rows=0, num_cols=0
        )
    )
    table.captions.append(RefItem(cref="#/texts/999"))
    with pytest.raises(ValueError, match="associated"):
        export_docling(doc)


def test_many_sparse_tables_are_bounded_before_grid_allocation():
    from docling_core.types.doc import TableData

    doc = DoclingDocument(name="sparse")
    for _ in range(20):
        doc.add_table(data=TableData(num_rows=100, num_cols=100, table_cells=[]))
    with pytest.raises(ValueError, match="max_total_table_cells"):
        export_docling(doc, max_total_table_cells=100000)
    with pytest.raises(ValueError, match="max_total_table_cells"):
        export_json(doc.export_to_dict(), max_total_table_cells=100000)
