"""Validate ownership graphs and resource limits before traversal."""

from __future__ import annotations
from typing import Any


def validate_document(document: Any, *, max_items: int = 100000) -> None:
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
        raise ValueError("max_items must be a positive integer")
    nodes = {
        document.body.self_ref: document.body,
        vars(document)["furniture"].self_ref: vars(document)["furniture"],
    }
    for field in type(document).model_fields:
        value = vars(document).get(field)
        if isinstance(value, list):
            for item in value:
                if hasattr(item, "self_ref"):
                    if item.self_ref in nodes:
                        raise ValueError("Duplicate document item reference")
                    nodes[item.self_ref] = item
    if len(nodes) > max_items:
        raise ValueError("Document exceeds max_items")
    parents: dict[str, str] = {}
    for item in nodes.values():
        for child in item.children:
            if child.cref not in nodes:
                raise ValueError("Unknown document child reference: " + child.cref)
            if child.cref in parents:
                raise ValueError("Document item has multiple ownership edges: " + child.cref)
            parents[child.cref] = item.self_ref
    for item in nodes.values():
        refs = []
        for field in ("captions", "footnotes", "references"):
            refs.extend(getattr(item, field, []) or [])
        for cell in getattr(getattr(item, "data", None), "table_cells", []):
            ref = getattr(cell, "ref", None)
            if ref is not None:
                refs.append(ref)
        if any(ref.cref not in nodes for ref in refs):
            raise ValueError("Unknown associated document reference")
    colors: dict[str, int] = {}
    for key in nodes:
        stack = [(key, False, 0)]
        while stack:
            ref, exiting, depth = stack.pop()
            if depth > 128:
                raise ValueError("Document nesting exceeds 128 levels")
            if exiting:
                colors[ref] = 2
                continue
            if colors.get(ref) == 1:
                raise ValueError("Document ownership graph contains a cycle")
            if colors.get(ref) == 2:
                continue
            colors[ref] = 1
            stack.append((ref, True, depth))
            stack.extend((child.cref, False, depth + 1) for child in reversed(nodes[ref].children))
