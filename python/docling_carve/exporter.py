"""Export Docling's document model directly to Carve source and provenance."""

from __future__ import annotations

from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image
from ._native import render_ast_json, ENGINE_VERSION, __version__


from .result import DoclingExport, DoclingExportError
from .validation import validate_document


def export_docling(
    document: Any,
    *,
    asset_dir: Optional[Path] = None,
    asset_prefix: str = "assets",
    strict: bool = False,
    max_table_cells: int = 100000,
    max_total_table_cells: int = 1000000,
    included_content_layers: Optional[Any] = None,
    max_items: int = 100000,
    max_diagnostics: int = 1000,
    max_asset_bytes: int = 16000000,
    max_image_pixels: int = 40000000,
    max_total_asset_bytes: int = 64000000,
    root: Optional[Any] = None,
) -> DoclingExport:
    """Export headings, text, links, tables, and figures without Markdown.

    Images are returned as PNG bytes. Pass asset_dir to write them after strict
    checks pass; asset_prefix is their URL directory relative to the document.
    Requires docling-core on Python 3.10+.
    """
    try:
        from docling_core.types.doc import (
            PictureItem,
            TableItem,
            TextItem,
            GroupItem,
            InlineGroup,
            CodeItem,
            FloatingItem,
            RichTableCell,
            ContentLayer,
            ListGroup,
            ListItem,
        )
    except ImportError as exc:
        raise ImportError(
            "Install docling-carve on Python 3.10+ to export Docling documents"
        ) from exc
    if (
        isinstance(max_table_cells, bool)
        or not isinstance(max_table_cells, int)
        or max_table_cells < 1
    ):
        raise ValueError("max_table_cells must be a positive integer")
    if not isinstance(strict, bool):
        raise ValueError("strict must be boolean")
    if not isinstance(asset_prefix, str):
        raise ValueError("asset_prefix must be a string")
    if included_content_layers is not None and not isinstance(
        included_content_layers, (list, tuple, set)
    ):
        raise ValueError("included_content_layers must be a collection of layer names")
    if not re.fullmatch(r"[A-Za-z0-9._/-]*", asset_prefix):
        raise ValueError("asset_prefix must contain URL path characters only")
    if (
        asset_prefix.startswith(("/", "\\"))
        or ":" in asset_prefix
        or any(p == ".." for p in asset_prefix.replace("\\", "/").split("/"))
    ):
        raise ValueError("asset_prefix must be a relative URL directory")
    asset_prefix = Path(asset_prefix).as_posix() if asset_prefix else ""
    if asset_prefix == ".":
        asset_prefix = ""
    validate_document(document, max_items=max_items)
    for label, limit in (
        ("max_total_table_cells", max_total_table_cells),
        ("max_diagnostics", max_diagnostics),
        ("max_asset_bytes", max_asset_bytes),
        ("max_image_pixels", max_image_pixels),
        ("max_total_asset_bytes", max_total_asset_bytes),
    ):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < (0 if label == "max_diagnostics" else 1)
        ):
            raise ValueError(label + " has an invalid limit")
    total_diagnostics = 0
    diagnostics: List[Dict[str, Any]] = []
    provenance: List[Dict[str, Any]] = []
    assets: Dict[str, bytes] = {}
    blocks: List[Dict[str, Any]] = []
    layers = (
        {ContentLayer.BODY}
        if included_content_layers is None
        else {ContentLayer(layer) for layer in included_content_layers}
    )
    items = list(
        document.iterate_items(
            root=root, with_groups=True, traverse_pictures=False, included_content_layers=layers
        )
    )
    for item, _ in items:
        if isinstance(item, TableItem):
            rows, cols = item.data.num_rows, item.data.num_cols
            if rows < 1 or cols < 1 or rows * cols > max_table_cells:
                raise ValueError(
                    item.self_ref + ": table dimensions must be positive and within max_table_cells"
                )
    total_table_cells = sum(
        max(0, item.data.num_rows) * max(0, item.data.num_cols)
        for item, _ in items
        if isinstance(item, TableItem)
    )
    if total_table_cells > max_total_table_cells:
        raise ValueError("Document exceeds max_total_table_cells")
    captions = {
        ref.cref for item, _ in items if isinstance(item, FloatingItem) for ref in item.captions
    }
    consumed = set(captions)
    if root is not None:
        consumed.discard(root.self_ref)
    for candidate, _ in items:
        if isinstance(candidate, TableItem):
            for cell in candidate.data.table_cells:
                if isinstance(cell, RichTableCell):
                    consumed.update(
                        node.self_ref
                        for node, _ in document.iterate_items(
                            root=cell.ref.resolve(document),
                            with_groups=True,
                            traverse_pictures=False,
                        )
                    )

    def diagnostic(item: Any, code: str, message: str, path: Optional[str] = None) -> None:
        nonlocal total_diagnostics
        total_diagnostics += 1
        if len(diagnostics) < max_diagnostics:
            diagnostics.append(
                {"code": code, "ref": item.self_ref, "path": path, "message": message}
            )

    def text_nodes(item: Any, text: Optional[str] = None) -> List[Dict[str, Any]]:
        value = item.text if text is None else text
        normalized = re.sub(r"(?:(?:\r\n|[\r\n])[ \t]*){2,}", " ", value)
        if normalized != value:
            diagnostic(
                item,
                "text-linebreaks-normalized",
                "Blank lines inside one text item became spaces.",
            )
        if not normalized:
            return []
        nodes = [{"type": "text", "value": normalized}]
        formatting = getattr(item, "formatting", None)
        if formatting:
            mapping = [
                ("bold", "strong"),
                ("italic", "emphasis"),
                ("underline", "underline"),
                ("strikethrough", "strike"),
            ]
            for key, kind in mapping:
                if getattr(formatting, key, False):
                    nodes = [{"type": kind, "children": nodes}]
            script = getattr(getattr(formatting, "script", None), "value", None)
            if script in ("sub", "super"):
                nodes = [
                    {"type": "subscript" if script == "sub" else "superscript", "children": nodes}
                ]
        link = getattr(item, "hyperlink", None)
        if link is not None:
            nodes = [{"type": "link", "href": str(link), "children": nodes}]
        return nodes

    def caption_nodes(item: Any) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        for ref in item.captions:
            caption = ref.resolve(document)
            if nodes:
                nodes.append({"type": "text", "value": " "})
            value = re.sub(r"\r\n|[\r\n]", " ", caption.text)
            if value != caption.text:
                diagnostic(
                    caption,
                    "caption-linebreaks-normalized",
                    "Caption line breaks became spaces in native source.",
                )
            nodes.extend(text_nodes(caption, value))
        return nodes

    def table(item: Any, path: str) -> Optional[Dict[str, Any]]:
        provenance_start = len(provenance)
        table_diagnostic_start = len(diagnostics)
        data = item.data
        nr, nc = data.num_rows, data.num_cols
        if nr < 1 or nc < 1 or nr * nc > max_table_cells:
            raise ValueError(
                "%s: table dimensions must be positive and within max_table_cells" % item.self_ref
            )
        grid: List[List[Optional[Dict[str, Any]]]] = [[None for _ in range(nc)] for _ in range(nr)]
        for cell in data.table_cells:
            r0, r1 = cell.start_row_offset_idx, cell.end_row_offset_idx
            c0, c1 = cell.start_col_offset_idx, cell.end_col_offset_idx
            if not (0 <= r0 < r1 <= nr and 0 <= c0 < c1 <= nc):
                raise ValueError("%s: cell is outside the table" % item.self_ref)
            if r1 - r0 != cell.row_span or c1 - c0 != cell.col_span:
                raise ValueError("%s: inconsistent cell span and offsets" % item.self_ref)
            value = cell.text
            cell_path = "%s/rows/%d/cells/%d" % (path, r0, c0)
            if isinstance(cell, RichTableCell):
                root = cell.ref.resolve(document)
                descendants = list(
                    document.iterate_items(root=root, with_groups=True, traverse_pictures=False)
                )
                consumed.update(node.self_ref for node, _ in descendants)
                value = " ".join(node.text for node, _ in descendants if isinstance(node, TextItem))
                for node, _ in descendants:
                    if isinstance(node, TextItem):
                        provenance.append(
                            {
                                "path": cell_path,
                                "ref": node.self_ref,
                                "role": "rich-cell-text",
                                "pages": [prov.model_dump(mode="json") for prov in node.prov],
                            }
                        )
                diagnostic(
                    item, "block-cell-flattened", "Rich cell blocks became inline text.", cell_path
                )
            if not value.strip() and (cell.row_span > 1 or cell.col_span > 1):
                value = "[empty]"
                diagnostic(
                    item,
                    "empty-merged-cell-placeholder",
                    "An empty merged cell uses [empty] to retain its geometry in native source.",
                    cell_path,
                )
            if "\n" in value or "\r" in value:
                value = re.sub(r"\r\n|[\r\n]", " ", value)
                diagnostic(
                    item,
                    "cell-linebreaks-normalized",
                    "Cell line breaks became spaces in native source.",
                    cell_path,
                )
            origin: Dict[str, Any] = {
                "type": "table_cell",
                "header": cell.column_header or cell.row_header,
                "children": [{"type": "text", "value": value}],
            }
            if cell.row_span > 1:
                origin["rowspan"] = cell.row_span
            if cell.col_span > 1:
                origin["colspan"] = cell.col_span
            if cell.row_section:
                diagnostic(
                    item,
                    "row-section-flattened",
                    "Row-section role is not represented in source.",
                    cell_path,
                )
            if cell.fillable:
                diagnostic(
                    item,
                    "fillable-cell-flattened",
                    "Fillable-cell behavior is not represented in source.",
                    cell_path,
                )
            for r in range(r0, r1):
                for c in range(c0, c1):
                    if grid[r][c] is not None:
                        raise ValueError("%s: overlapping table cells" % item.self_ref)
                    grid[r][c] = (
                        origin
                        if (r, c) == (r0, c0)
                        else {
                            "type": "table_cell",
                            "header": False,
                            "span": "colspan" if r == r0 else "rowspan",
                            "children": [],
                        }
                    )
            if cell.bbox is not None:
                entry = {
                    "path": cell_path,
                    "ref": item.self_ref,
                    "bbox": cell.bbox.model_dump(mode="json"),
                    "pages": [],
                }
                if len(item.prov) == 1:
                    entry["page_no"] = item.prov[0].page_no
                    entry["pages"] = [{"page_no": item.prov[0].page_no, "bbox": entry["bbox"]}]
                else:
                    diagnostic(
                        item,
                        "cell-page-ambiguous",
                        "Cell bounding box has no unique page association.",
                        cell_path,
                    )
                provenance.append(entry)
        caption = caption_nodes(item)
        rows = [
            {
                "type": "table_row",
                "cells": [
                    cell
                    if cell is not None
                    else {"type": "table_cell", "header": False, "children": []}
                    for cell in row
                ],
            }
            for row in grid
        ]
        retained = [
            index
            for index, row in enumerate(rows)
            if any(
                cell.get("span")
                or any(node.get("value", "").strip() for node in cell.get("children", []))
                for cell in row["cells"]
            )
        ]
        if len(retained) != len(rows):
            retained_set = set(retained)
            for index in range(len(rows)):
                if index not in retained_set:
                    diagnostic(
                        item,
                        "blank-table-row-omitted",
                        "Blank source row %d has no native Carve spelling and was omitted." % index,
                        path if retained or caption else None,
                    )
            remap = {old: new for new, old in enumerate(retained)}
            for entry in provenance[provenance_start:] + diagnostics[table_diagnostic_start:]:
                entry_path = entry.get("path")
                if entry_path and entry_path.startswith(path + "/rows/"):
                    suffix = entry_path[len(path + "/rows/") :]
                    row, rest = suffix.split("/", 1)
                    entry["path"] = (
                        path + "/rows/%d/" % remap[int(row)] + rest if int(row) in remap else None
                    )
            rows = [rows[index] for index in retained]
        if not rows:
            return {"type": "paragraph", "children": caption} if caption else None
        return {"type": "table", "rows": rows, "caption": caption}

    contexts: List[Dict[str, Any]] = []
    for item, depth in items:
        while contexts and depth <= contexts[-1]["depth"]:
            contexts.pop()
        if item.self_ref in consumed:
            continue
        destination = (
            contexts[-1]["children"] if contexts and contexts[-1]["kind"] == "item" else blocks
        )
        destination_path = (
            contexts[-1]["path"] + "/children"
            if contexts and contexts[-1]["kind"] == "item"
            else "/children"
        )
        managed_list_item = (
            isinstance(item, ListItem) and contexts and contexts[-1]["kind"] == "list"
        )
        if managed_list_item:
            owner = contexts[-1]
            item_path = owner["path"] + "/items/%d" % len(owner["node"]["items"])
            list_item = {"type": "list_item", "children": []}
            owner["node"]["items"].append(list_item)
            contexts.append(
                {
                    "kind": "item",
                    "depth": depth,
                    "path": item_path,
                    "children": list_item["children"],
                }
            )
            destination = list_item["children"]
            destination_path = item_path + "/children"
            marker = re.match(r"^(\d+)[.)]?$", item.marker or "")
            expected = owner["start"] + len(owner["node"]["items"]) - 1
            if (
                item.enumerated != owner["node"]["ordered"]
                or marker
                and int(marker.group(1)) != expected
            ):
                diagnostic(
                    item,
                    "list-numbering-normalized",
                    "List numbering uses one consecutive marker sequence.",
                    item_path,
                )
            provenance.append(
                {
                    "path": item_path,
                    "ref": item.self_ref,
                    "pages": [v.model_dump(mode="json") for v in item.prov],
                    "depth": depth,
                }
            )
        if isinstance(item, ListGroup):
            children = [ref.resolve(document) for ref in item.children]
            if children and all(isinstance(child, ListItem) for child in children):
                ordered = children[0].enumerated
                marker = re.match(r"^(\d+)[.)]?$", children[0].marker or "")
                start = int(marker.group(1)) if ordered and marker else 1
                list_path = destination_path + "/%d" % len(destination)
                node = {"type": "list", "ordered": ordered, "tight": True, "items": []}
                if ordered and start != 1:
                    node["start"] = start
                destination.append(node)
                contexts.append(
                    {
                        "kind": "list",
                        "depth": depth,
                        "path": list_path,
                        "node": node,
                        "start": start,
                    }
                )
                provenance.append(
                    {"path": list_path, "ref": item.self_ref, "pages": [], "depth": depth}
                )
                if getattr(item, "meta", None):
                    diagnostic(
                        item,
                        "metadata-not-exported",
                        "List metadata is retained in the input sidecar.",
                        list_path,
                    )
                continue
            if not children:
                diagnostic(
                    item, "empty-list-omitted", "Empty list has no source items and was omitted."
                )
                continue
        if isinstance(item, GroupItem) and not isinstance(item, InlineGroup):
            if getattr(item, "meta", None):
                diagnostic(
                    item, "metadata-not-exported", "Group metadata is not represented in source."
                )
            if item.self_ref != document.body.self_ref:
                diagnostic(
                    item,
                    "group-flattened",
                    "Group nesting is flattened; children remain in reading order.",
                )
            continue
        path = destination_path + "/%d" % len(destination)
        diagnostic_start = len(diagnostics)
        pages = [prov.model_dump(mode="json") for prov in getattr(item, "prov", [])]
        block: Optional[Dict[str, Any]] = None
        if isinstance(item, InlineGroup):
            runs = list(
                document.iterate_items(
                    root=item,
                    with_groups=True,
                    traverse_pictures=False,
                    included_content_layers=layers,
                )
            )
            consumed.update(child.self_ref for child, _ in runs if child.self_ref != item.self_ref)
            inline = []
            for child, _ in runs:
                if isinstance(child, TextItem):
                    inline.extend(text_nodes(child))
                    pages.extend(
                        prov.model_dump(mode="json") for prov in getattr(child, "prov", [])
                    )
                    if child.label.value not in ("text", "paragraph", "caption"):
                        diagnostic(
                            child,
                            "inline-role-flattened",
                            "Inline text role became a formatted text run.",
                            path,
                        )
                elif not isinstance(child, GroupItem):
                    diagnostic(
                        child,
                        "inline-item-dropped",
                        "Non-text inline item is not represented in the paragraph.",
                        path,
                    )
            block = {"type": "paragraph", "children": inline} if inline else None
        elif isinstance(item, TableItem):
            block = table(item, path)
        elif isinstance(item, PictureItem):
            try:
                image = item.get_image(document)
            except Image.DecompressionBombError as error:
                raise ValueError("Image exceeds safe decoding dimensions") from error
            except (OSError, ValueError, KeyError, IndexError):
                image = None
            if image is None:
                diagnostic(
                    item,
                    "image-unavailable",
                    "Figure image is unavailable; caption text remains.",
                    path,
                )
                block = {"type": "paragraph", "children": caption_nodes(item)}
            else:
                if image.width * image.height > max_image_pixels:
                    raise ValueError("Image exceeds max_image_pixels")
                buffer = BytesIO()
                if image.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"):
                    image = image.convert("RGB")
                    diagnostic(
                        item,
                        "image-mode-converted",
                        "Image color mode was converted to RGB for PNG output.",
                        path,
                    )
                image.save(buffer, format="PNG")
                payload = buffer.getvalue()
                if len(payload) > max_asset_bytes:
                    raise ValueError("Figure exceeds max_asset_bytes")
                name = "figure-%s.png" % sha256(payload).hexdigest()
                assets[name] = payload
                if sum(len(value) for value in assets.values()) > max_total_asset_bytes:
                    raise ValueError("Images exceed max_total_asset_bytes")
                caption = caption_nodes(item)
                alt = " ".join(
                    re.sub(r"\r\n|[\r\n]", " ", ref.resolve(document).text) for ref in item.captions
                )
                target = {
                    "type": "image",
                    "src": asset_prefix.rstrip("/") + "/" + name if asset_prefix else name,
                    "alt": alt,
                }
                block = (
                    {"type": "figure", "target": target, "caption": caption}
                    if caption
                    else {"type": "paragraph", "children": [target]}
                )
        elif isinstance(item, TextItem):
            label = item.label.value
            if label in ("title", "section_header"):
                level = getattr(item, "level", 1)
                if level > 6:
                    diagnostic(
                        item,
                        "heading-level-clamped",
                        "Heading levels above six become level six.",
                        path,
                    )
                heading_text = item.text
                if "\n" in heading_text or "\r" in heading_text:
                    heading_text = re.sub(r"\r\n|[\r\n]", " ", heading_text)
                    diagnostic(
                        item,
                        "heading-linebreaks-normalized",
                        "Heading line breaks became spaces in native source.",
                        path,
                    )
                if not heading_text.strip():
                    diagnostic(
                        item,
                        "empty-heading-omitted",
                        "An empty heading has no source content.",
                        path,
                    )
                block = {
                    "type": "heading",
                    "level": min(level, 6),
                    "children": text_nodes(item, heading_text) if heading_text.strip() else [],
                }
            elif label == "code":
                block = {
                    "type": "code_block",
                    "content": item.text,
                    "lang": str(
                        getattr(getattr(item, "code_language", None), "value", "") or ""
                    ).lower(),
                }
                if block["lang"] == "unknown":
                    block["lang"] = ""
                if isinstance(item, CodeItem) and item.captions:
                    block = {"type": "figure", "target": block, "caption": caption_nodes(item)}
            elif label == "formula" and not item.text.strip():
                diagnostic(
                    item,
                    "empty-formula-omitted",
                    "Empty formula has no native math spelling and was omitted.",
                )
            elif label == "formula":
                block = {
                    "type": "paragraph",
                    "children": [{"type": "math", "display": True, "content": item.text}],
                }
            else:
                block = {"type": "paragraph", "children": text_nodes(item)}
                if label not in ("text", "paragraph", "caption") and not managed_list_item:
                    diagnostic(
                        item, "item-role-flattened", "%s role became a paragraph." % label, path
                    )
        else:
            diagnostic(
                item,
                "unsupported-item",
                "Unsupported item %s; inspect its source reference." % type(item).__name__,
            )
        if (
            block is not None
            and block.get("type") in ("paragraph", "heading")
            and not block.get("children")
        ):
            block = None
        if block is None:
            for entry in diagnostics[diagnostic_start:]:
                if entry.get("path") == path:
                    entry["path"] = None
        if block is not None:
            destination.append(block)
            if isinstance(item, FloatingItem):
                for ref in item.captions:
                    caption_item = ref.resolve(document)
                    provenance.append(
                        {
                            "path": path,
                            "ref": caption_item.self_ref,
                            "role": "caption",
                            "pages": [prov.model_dump(mode="json") for prov in caption_item.prov],
                        }
                    )
            provenance.append({"path": path, "ref": item.self_ref, "pages": pages, "depth": depth})
        if isinstance(item, FloatingItem):
            for key in ("footnotes", "references"):
                if getattr(item, key, None):
                    diagnostic(
                        item,
                        "floating-association-not-exported",
                        "%s associations are not represented in source." % key,
                        path if block else None,
                    )
        for key in ("meta", "comments"):
            if getattr(item, key, None):
                diagnostic(
                    item,
                    "metadata-not-exported",
                    "%s metadata is not represented in source." % key,
                    path if block else None,
                )

    ast = {"type": "document", "children": blocks, "srcByteLength": 0}
    value = render_ast_json(json.dumps(ast, ensure_ascii=False))
    result = DoclingExport(
        value=value,
        ast=ast,
        diagnostics=diagnostics,
        provenance=provenance,
        assets=assets,
        source={
            "name": document.name,
            "origin": document.origin.model_dump(mode="json") if document.origin else None,
        },
        asset_prefix=asset_prefix,
        total_diagnostics=total_diagnostics,
        max_diagnostics=max_diagnostics,
        document=document.model_dump(
            mode="json", by_alias=True, exclude_none=True, round_trip=True
        ),
        versions={
            "carve": ENGINE_VERSION,
            "docling-carve": __version__,
            "docling-core": version("docling-core"),
        },
    )
    if strict and total_diagnostics:
        raise DoclingExportError(result)
    if asset_dir is not None and assets:
        destination = Path(asset_dir)
        destination.mkdir(parents=True, exist_ok=True)
        for name, payload in assets.items():
            target = destination / name
            if target.is_symlink():
                raise ValueError("Asset output must not replace a symlink")
            target.write_bytes(payload)
    return result
