"""Versioned output contract and artifact writing."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any


@dataclass
class DoclingExport:
    value: str
    ast: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    provenance: list[dict[str, Any]]
    assets: dict[str, bytes] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)
    asset_prefix: str = "assets"
    total_diagnostics: int = 0
    max_diagnostics: int = 1000
    document: dict[str, Any] = field(default_factory=dict)
    assessment: str = "docling-carve-v1"
    complete: bool = False

    def to_dict(
        self,
        *,
        include_assets: bool = False,
        include_ast: bool = True,
        include_document: bool = False,
    ) -> dict[str, Any]:
        output: dict[str, Any] = {
            "schema_version": "1",
            "assessment": self.assessment,
            "complete": self.complete,
            "value": self.value,
            "source": self.source,
            "versions": self.versions,
            "diagnostics": self.diagnostics,
            "total_diagnostics": self.total_diagnostics,
            "max_diagnostics": self.max_diagnostics,
            "truncated": self.total_diagnostics > len(self.diagnostics),
            "provenance": self.provenance,
            "checked": [
                "reading order",
                "nested lists",
                "text formatting and links",
                "headings",
                "table geometry and captions",
                "image assets",
                "available provenance",
            ],
            "unchecked": [
                "extraction accuracy",
                "visual layout",
                "host rendering",
                "final artifacts",
                "excluded content layers",
                "source spelling",
            ],
            "assets": [],
        }
        for name, payload in sorted(self.assets.items()):
            asset = {
                "name": name,
                "media_type": "image/png",
                "size": len(payload),
                "sha256": sha256(payload).hexdigest(),
                "path": self.asset_prefix.rstrip("/") + "/" + name if self.asset_prefix else name,
            }
            if include_assets:
                asset["base64"] = base64.b64encode(payload).decode("ascii")
            output["assets"].append(asset)
        if include_ast:
            output["ast"] = self.ast
        if include_document:
            output["document"] = self.document
        return output

    def write_bundle(
        self, directory: str | Path, *, overwrite: bool = False, include_document: bool = True
    ) -> Path:
        """Write a complete bundle, refusing an existing destination by default."""
        from ._native import to_html

        target = Path(directory).absolute()
        if target.is_symlink():
            raise ValueError("Bundle destination must not be a symlink")
        if target.exists() and not overwrite:
            raise FileExistsError(target)
        if target.exists() and overwrite:
            marker = target / "report.json"
            try:
                manifest = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError("Only a managed docling-carve bundle can be replaced") from error
            if (
                manifest.get("assessment") != "docling-carve-v1"
                or manifest.get("schema_version") != "1"
            ):
                raise ValueError("Only a managed docling-carve bundle can be replaced")
            owned = {"document.crv", "report.json", "ast.json", "preview.html", "docling.json"}
            owned.update(asset["path"] for asset in manifest.get("assets", []))
            if any(
                path.is_symlink()
                or path.is_file()
                and path.relative_to(target).as_posix() not in owned
                for path in target.rglob("*")
            ):
                raise ValueError("Bundle contains files outside its managed artifacts")
        if target.exists() and not target.is_dir():
            raise ValueError("Bundle destination must be a directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".docling-carve-", dir=target.parent))
        try:
            (stage / "document.crv").write_text(self.value, encoding="utf-8")
            (stage / "report.json").write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (stage / "ast.json").write_text(
                json.dumps(self.ast, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (stage / "preview.html").write_text(to_html(self.value), encoding="utf-8")
            if include_document:
                (stage / "docling.json").write_text(
                    json.dumps(self.document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            asset_directory = stage / self.asset_prefix
            if not asset_directory.resolve().is_relative_to(stage.resolve()):
                raise ValueError("Asset prefix escapes the bundle")
            if self.assets:
                asset_directory.mkdir(parents=True, exist_ok=True)
            for name, payload in self.assets.items():
                if Path(name).name != name or name in ("", ".", ".."):
                    raise ValueError("Invalid asset name")
                (asset_directory / name).write_bytes(payload)
            if target.exists():
                backup = Path(tempfile.mkdtemp(prefix=".docling-carve-backup-", dir=target.parent))
                backup.rmdir()
                target.rename(backup)
                try:
                    stage.rename(target)
                except BaseException:
                    backup.rename(target)
                    raise
                shutil.rmtree(backup)
            else:
                stage.rename(target)
            return target
        finally:
            if stage.exists():
                shutil.rmtree(stage)


class DoclingExportError(ValueError):
    def __init__(self, result: DoclingExport):
        self.result = result
        super().__init__(
            "Docling export requires review of %d diagnostic(s)" % result.total_diagnostics
        )
