"""Exercise the installed adapter against Docling's actual document model."""

import json

from docling_carve import _native as carve
import pytest

from docling_core.types.doc import (
    DoclingDocument,
    DocItemLabel,
    ImageRef,
    TableData,
    TableCell,
    ProvenanceItem,
    BoundingBox,
)
from PIL import Image
from docling_carve import export_docling, DoclingExportError


carve.parse = lambda value: json.loads(carve.parse_json(value))


def cell(text, r0, r1, c0, c1, header=False):
    return TableCell(
        text=text,
        start_row_offset_idx=r0,
        end_row_offset_idx=r1,
        start_col_offset_idx=c0,
        end_col_offset_idx=c1,
        row_span=r1 - r0,
        col_span=c1 - c0,
        column_header=header,
    )


def table_document():
    doc = DoclingDocument(name="limits")
    doc.add_heading("Limits", level=2)
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Operating limits")
    doc.add_table(
        data=TableData(
            num_rows=3,
            num_cols=3,
            table_cells=[
                cell("System", 0, 1, 0, 1, True),
                cell("Limit", 0, 1, 1, 3, True),
                cell("A", 1, 3, 0, 1),
                cell("Cold", 1, 2, 1, 2),
                cell("20", 1, 2, 2, 3),
                cell("Hot", 2, 3, 1, 2),
                cell("10", 2, 3, 2, 3),
            ],
        ),
        caption=caption,
        prov=ProvenanceItem(page_no=4, bbox=BoundingBox(l=0, t=100, r=100, b=0), charspan=(0, 1)),
    )
    return doc


def test_table_geometry_caption_and_provenance_survive():
    result = export_docling(table_document(), strict=True)
    assert result.diagnostics == []
    html = carve.to_html(result.value)
    assert 'colspan="2"' in html
    assert 'rowspan="2"' in html
    assert "<caption>Operating limits</caption>" in html
    assert html.count("Operating limits") == 1
    assert ">Cold<" in html and ">Hot<" in html
    assert result.provenance[-1]["pages"][0]["page_no"] == 4
    assert result.provenance[-1]["ref"] == "#/tables/0"
    assert carve.to_carve(result.value) == result.value
    assert result.complete is False


def test_literal_text_does_not_become_carve_markup():
    doc = DoclingDocument(name="literal")
    doc.add_text(label=DocItemLabel.TEXT, text="*literal* /plain/ | =literal= </#other>")
    output = carve.to_html(export_docling(doc).value)
    assert "<strong>" not in output
    assert "<em>" not in output
    assert "*literal*" in output
    assert "&lt;/#other&gt;" in output


def test_figures_assets_and_captions(tmp_path):
    doc = DoclingDocument(name="figure")
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="A sample figure")
    doc.add_picture(
        image=ImageRef.from_pil(Image.new("RGB", (3, 2), color="red"), dpi=72), caption=caption
    )
    result = export_docling(doc, asset_dir=tmp_path, strict=True)
    assert len(result.assets) == 1
    name, payload = next(iter(result.assets.items()))
    assert (tmp_path / name).read_bytes() == payload
    assert payload.startswith(b"\x89PNG")
    html = carve.to_html(result.value)
    assert "<figure>" in html and "<figcaption>A sample figure</figcaption>" in html
    assert 'src="assets/%s"' % name in html
    assert export_docling(doc).value == result.value


def test_strict_review_happens_before_asset_writes(tmp_path):
    doc = DoclingDocument(name="review")
    doc.add_picture(image=ImageRef.from_pil(Image.new("RGB", (2, 2)), dpi=72))
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="Furniture in body")
    with pytest.raises(DoclingExportError) as error:
        export_docling(doc, asset_dir=tmp_path / "assets", strict=True)
    assert any(d["code"] == "item-role-flattened" for d in error.value.result.diagnostics)
    assert not (tmp_path / "assets").exists()


def test_missing_image_retains_caption_and_reports_degradation():
    doc = DoclingDocument(name="missing")
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Visible caption")
    doc.add_picture(caption=caption)
    result = export_docling(doc)
    assert "Visible caption" in result.value
    assert result.diagnostics[0]["code"] == "image-unavailable"


def test_overlap_and_resource_limits_are_refused():
    doc = table_document()
    with pytest.raises(ValueError, match="max_table_cells"):
        export_docling(doc, max_table_cells=8)
    doc.tables[0].data.table_cells.append(cell("overlap", 1, 2, 0, 1))
    with pytest.raises(ValueError, match="overlapping"):
        export_docling(doc)


def test_native_ast_writer_refuses_invalid_or_unspellable_trees():
    with pytest.raises(ValueError):
        carve.render_ast_json('{"type":"document","children":[{"type":"bogus"}],"srcByteLength":0}')
    assert carve.render_ast_json(
        json.dumps(
            {
                "type": "document",
                "children": [
                    {"type": "paragraph", "children": [{"type": "text", "value": "*text*"}]}
                ],
                "srcByteLength": 0,
            }
        )
    ).startswith("\\*")


def test_formatting_and_links_use_the_native_ast_writer():
    from docling_core.types.doc import Formatting, Script

    doc = DoclingDocument(name="formatting")
    doc.add_text(
        label=DocItemLabel.TEXT,
        text="marked",
        formatting=Formatting(
            bold=True, italic=True, underline=True, strikethrough=True, script=Script.SUPER
        ),
        hyperlink="https://example.com/",
    )
    html = carve.to_html(export_docling(doc, strict=True).value)
    for tag in ("strong", "em", "u", "s", "sup"):
        assert "<%s>" % tag in html
    assert 'href="https://example.com/"' in html


def test_a_cell_spanning_both_axes_preserves_its_geometry():
    doc = DoclingDocument(name="rectangle")
    doc.add_table(
        data=TableData(
            num_rows=2,
            num_cols=3,
            table_cells=[
                cell("merged", 0, 2, 0, 2),
                cell("right top", 0, 1, 2, 3),
                cell("right bottom", 1, 2, 2, 3),
            ],
        )
    )
    html = carve.to_html(export_docling(doc, strict=True).value)
    assert 'rowspan="2"' in html and 'colspan="2"' in html
    assert html.count("merged") == 1
    assert "right top" in html and "right bottom" in html


def test_rich_cell_text_is_kept_once_with_a_review_diagnostic():
    from docling_core.types.doc import RichTableCell

    doc = DoclingDocument(name="rich")
    group = doc.add_group()
    doc.add_text(label=DocItemLabel.TEXT, text="Rich cell text", parent=group)
    doc.add_table(
        data=TableData(
            num_rows=1,
            num_cols=1,
            table_cells=[
                RichTableCell(
                    ref=group.get_ref(),
                    text="",
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                )
            ],
        )
    )
    result = export_docling(doc)
    assert result.value.count("Rich cell text") == 1
    assert any(d["code"] == "block-cell-flattened" for d in result.diagnostics)


def test_code_captions_and_empty_formatted_text():
    from docling_core.types.doc import CodeLanguageLabel, Formatting

    doc = DoclingDocument(name="code")
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Example code")
    doc.add_code('print("hi")', code_language=CodeLanguageLabel.PYTHON, caption=caption)
    doc.add_text(label=DocItemLabel.TEXT, text="", formatting=Formatting(bold=True))
    result = export_docling(doc, strict=True)
    assert "```python" in result.value
    assert result.value.count("Example code") == 1
    assert "print" in carve.to_html(result.value)


def test_blank_rows_are_reported_instead_of_crashing():
    doc = DoclingDocument(name="blanks")
    doc.add_table(
        data=TableData(
            num_rows=3,
            num_cols=1,
            table_cells=[cell("first", 0, 1, 0, 1), cell("last", 2, 3, 0, 1)],
        )
    )
    result = export_docling(doc)
    assert [d["code"] for d in result.diagnostics] == ["blank-table-row-omitted"]
    assert "first" in result.value and "last" in result.value
    with pytest.raises(DoclingExportError):
        export_docling(doc, strict=True)


def test_body_layers_and_inline_groups_preserve_reading_flow():
    from docling_core.types.doc import ContentLayer, Formatting

    doc = DoclingDocument(name="flow")
    doc.add_text(
        label=DocItemLabel.PAGE_HEADER, text="Page furniture", content_layer=ContentLayer.FURNITURE
    )
    group = doc.add_inline_group()
    doc.add_text(label=DocItemLabel.TEXT, text="Hello ", parent=group)
    doc.add_text(
        label=DocItemLabel.TEXT, text="bold", parent=group, formatting=Formatting(bold=True)
    )
    doc.add_text(label=DocItemLabel.TEXT, text=" world.", parent=group)
    result = export_docling(doc, strict=True)
    assert "Page furniture" not in result.value
    assert carve.to_html(result.value) == "<p>Hello <strong>bold</strong> world.</p>"


def test_blank_lines_in_a_text_item_require_review_and_do_not_split_its_ast():
    doc = DoclingDocument(name="newlines")
    doc.add_text(label=DocItemLabel.TEXT, text="first\n\nsecond")
    result = export_docling(doc)
    assert result.diagnostics[0]["code"] == "text-linebreaks-normalized"
    assert len(carve.parse(result.value)["children"]) == 1


def test_empty_merged_cell_retains_geometry_with_a_review_placeholder():
    doc = DoclingDocument(name="empty merge")
    doc.add_table(data=TableData(num_rows=2, num_cols=1, table_cells=[cell("", 0, 2, 0, 1)]))
    result = export_docling(doc)
    assert 'rowspan="2"' in carve.to_html(result.value)
    assert result.diagnostics[0]["code"] == "empty-merged-cell-placeholder"
    with pytest.raises(DoclingExportError):
        export_docling(doc, strict=True)


def test_inline_provenance_and_dropped_item_diagnostic_paths():
    doc = DoclingDocument(name="provenance")
    doc.add_picture()
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="")
    group = doc.add_inline_group()
    doc.add_text(
        label=DocItemLabel.TEXT,
        text="visible",
        parent=group,
        prov=ProvenanceItem(page_no=2, bbox=BoundingBox(l=0, t=10, r=10, b=0), charspan=(0, 7)),
    )
    result = export_docling(doc)
    assert result.provenance[-1]["pages"][0]["page_no"] == 2
    assert all(d["path"] is None for d in result.diagnostics)


def test_cell_bbox_has_a_page_or_an_ambiguity_diagnostic():
    doc = table_document()
    doc.tables[0].data.table_cells[0].bbox = BoundingBox(l=0, t=10, r=10, b=0)
    result = export_docling(doc, strict=True)
    assert next(p for p in result.provenance if "bbox" in p)["page_no"] == 4
    doc.tables[0].prov = []
    result = export_docling(doc)
    assert any(d["code"] == "cell-page-ambiguous" for d in result.diagnostics)


def test_unknown_code_language_empty_formula_and_cell_linebreaks():
    doc = DoclingDocument(name="remaining fallbacks")
    doc.add_code("x")
    doc.add_text(label=DocItemLabel.FORMULA, text="   ")
    doc.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[cell("x\ny", 0, 1, 0, 1)]))
    result = export_docling(doc)
    assert "language-unknown" not in carve.to_html(result.value)
    assert {d["code"] for d in result.diagnostics} == {
        "empty-formula-omitted",
        "cell-linebreaks-normalized",
    }
    assert ">x y<" in carve.to_html(result.value)


def test_caption_alt_and_carriage_return_blank_lines_are_reported():
    doc = DoclingDocument(name="line endings")
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="first\n\nsecond")
    doc.add_picture(image=ImageRef.from_pil(Image.new("RGB", (1, 1)), dpi=72), caption=caption)
    doc.add_text(label=DocItemLabel.TEXT, text="a\r\rb")
    result = export_docling(doc)
    html = carve.to_html(result.value)
    assert "<figure>" in html and "<figcaption>" in html and "<img " in html
    assert {d["code"] for d in result.diagnostics} == {
        "caption-linebreaks-normalized",
        "text-linebreaks-normalized",
    }
    assert len(carve.parse(result.value)["children"]) == 2
    with pytest.raises(DoclingExportError):
        export_docling(doc, strict=True)
