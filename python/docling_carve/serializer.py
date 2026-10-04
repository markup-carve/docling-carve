"""Docling serializer and provider interfaces for Carve output."""

from __future__ import annotations
from typing import Any
from docling_core.transforms.serializer.base import (
    BaseDocSerializer,
    BaseSerializerProvider,
    SerializationResult,
    Span,
)
from docling_core.types.doc import DocItem, DoclingDocument, FloatingItem, NodeItem
from ._native import render_ast_json
from .exporter import export_docling
from .result import DoclingExport
import json


class CarveDocSerializer(BaseDocSerializer):
    def __init__(self, doc: DoclingDocument, **options: Any):
        self.doc = doc
        self.options = options
        self.last_export: DoclingExport | None = None

    def serialize(self, *, item: NodeItem | None = None, **kwargs: Any) -> SerializationResult:
        if kwargs:
            raise TypeError("Pass exporter options when constructing CarveDocSerializer")
        self.last_export = export_docling(self.doc, root=item, **self.options)
        refs = {entry["ref"] for entry in self.last_export.provenance}
        nodes = [
            node
            for node, _ in self.doc.iterate_items(
                root=item, with_groups=True, traverse_pictures=False
            )
            if isinstance(node, DocItem) and node.self_ref in refs
        ]
        return SerializationResult(
            text=self.last_export.value, spans=[Span(item=node) for node in nodes]
        )

    def get_parts(self, item: NodeItem | None = None, **kwargs: Any) -> list[SerializationResult]:
        return [self.serialize(item=item, **kwargs)]

    @staticmethod
    def _inline(kind: str, text: str, **fields: Any) -> str:
        if not text:
            return ""
        node = {"type": kind, "children": [{"type": "text", "value": text}], **fields}
        ast = {
            "type": "document",
            "children": [{"type": "paragraph", "children": [node]}],
            "srcByteLength": 0,
        }
        return render_ast_json(json.dumps(ast)).rstrip("\n")

    def serialize_bold(self, text: str, **kwargs: Any) -> str:
        return self._inline("strong", text)

    def serialize_italic(self, text: str, **kwargs: Any) -> str:
        return self._inline("emphasis", text)

    def serialize_underline(self, text: str, **kwargs: Any) -> str:
        return self._inline("underline", text)

    def serialize_strikethrough(self, text: str, **kwargs: Any) -> str:
        return self._inline("strike", text)

    def serialize_subscript(self, text: str, **kwargs: Any) -> str:
        return self._inline("subscript", text)

    def serialize_superscript(self, text: str, **kwargs: Any) -> str:
        return self._inline("superscript", text)

    def serialize_hyperlink(self, text: str, hyperlink: Any, **kwargs: Any) -> str:
        return self._inline("link", text, href=str(hyperlink))

    def post_process(self, text: str, **kwargs: Any) -> str:
        return text

    def _references(self, refs: list) -> SerializationResult:
        results = [self.serialize(item=ref.resolve(self.doc)) for ref in refs]
        return SerializationResult(
            text="\n\n".join(result.text.rstrip("\n") for result in results),
            spans=[span for result in results for span in result.spans],
        )

    def serialize_captions(self, item: FloatingItem, **kwargs: Any) -> SerializationResult:
        return self._references(item.captions)

    def serialize_footnotes(self, item: FloatingItem, **kwargs: Any) -> SerializationResult:
        return self._references(item.footnotes)

    def serialize_annotations(self, item: DocItem, **kwargs: Any) -> SerializationResult:
        return self.serialize_meta(item, **kwargs)

    def serialize_meta(self, item: NodeItem, **kwargs: Any) -> SerializationResult:
        # The export report and original Docling JSON carry unsupported metadata.
        return SerializationResult()

    def get_excluded_refs(self, **kwargs: Any) -> set[str]:
        included = self.options.get("included_content_layers")
        if included is None:
            included = ["body"]
        return {
            item.self_ref
            for item, _ in self.doc.iterate_items(with_groups=True)
            if item.content_layer.value not in included
        }

    def requires_page_break(self) -> bool:
        return False


class CarveSerializerProvider(BaseSerializerProvider):
    def __init__(self, **options: Any):
        self.options = options

    def get_serializer(self, doc: DoclingDocument) -> CarveDocSerializer:
        return CarveDocSerializer(doc, **self.options)
