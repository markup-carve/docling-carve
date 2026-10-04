"""Command-line entry point for conversion, extraction, and service adapters."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any

from ._native import ENGINE_VERSION, __version__, to_html
from .json_api import export_json
from .result import DoclingExport, DoclingExportError


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--strict", action="store_true", help="refuse output when conversion diagnostics exist"
    )
    parser.add_argument(
        "--asset-root", type=Path, help="allow JSON image files contained in this directory"
    )
    parser.add_argument("--max-input-bytes", type=_positive, default=64_000_000)
    parser.add_argument("--max-items", type=_positive, default=100000)
    parser.add_argument("--max-table-cells", type=_positive, default=100000)
    parser.add_argument("--max-diagnostics", type=int, default=1000)
    parser.add_argument(
        "--layer",
        action="append",
        dest="layers",
        choices=["body", "furniture", "background", "invisible", "notes"],
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="extract an input document with the optional Docling pipeline",
    )
    parser.add_argument("--pdf-pipeline", choices=["standard", "native"], default="standard")
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument(
        "--allow-url",
        action="store_true",
        help="allow explicit HTTP(S) input URLs in extraction mode",
    )
    parser.add_argument("--max-pages", type=_positive, default=1000)
    parser.add_argument("--no-source-snapshot", action="store_true")
    parser.add_argument(
        "--force", action="store_true", help="replace existing output files or bundles"
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="docling-carve")
    root.add_argument(
        "--version",
        action="version",
        version=f"docling-carve {__version__} (Carve {ENGINE_VERSION})",
    )
    commands = root.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert", help="convert Docling JSON, or extract with --extract")
    convert.add_argument("inputs", nargs="+", help="input files; use - for Docling JSON on stdin")
    outputs = convert.add_mutually_exclusive_group()
    outputs.add_argument("-o", "--output", type=Path)
    outputs.add_argument(
        "--bundle", type=Path, help="write source, report, AST, preview, original JSON, and assets"
    )
    convert.add_argument(
        "--format", choices=["carve", "report-json", "ast-json", "html"], default="carve"
    )
    convert.add_argument(
        "--report", type=Path, help="write a JSON report alongside a single output"
    )
    convert.add_argument("--assets-dir", type=Path, help="write returned image assets")
    convert.add_argument("--keep-going", action="store_true", help="continue after a failed input")
    _common(convert)
    batch = commands.add_parser("batch", help="convert matching files to one bundle per input")
    batch.add_argument("directory", type=Path)
    batch.add_argument("--output-dir", type=Path, required=True)
    batch.add_argument("--pattern", default="**/*.json")
    batch.add_argument("--keep-going", action="store_true")
    _common(batch)
    serve = commands.add_parser("serve", help="start the optional HTTP service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=_positive, default=8080)
    serve.add_argument("--max-input-bytes", type=_positive, default=16_000_000)
    mcp = commands.add_parser("mcp", help="start the optional MCP server over stdio")
    mcp.add_argument(
        "--root", type=Path, help="allow extraction from files contained under this root"
    )
    commands.add_parser("capabilities", help="print versions and supported interfaces as JSON")
    return root


def _result(
    source: str, args: argparse.Namespace, *, asset_prefix: str = "assets"
) -> DoclingExport:
    options: dict[str, Any] = {
        "strict": args.strict,
        "max_items": args.max_items,
        "max_table_cells": args.max_table_cells,
        "max_diagnostics": args.max_diagnostics,
        "included_content_layers": args.layers,
        "asset_prefix": asset_prefix,
    }
    if args.extract:
        if source == "-":
            raise ValueError("Extraction needs a file or explicit URL; stdin accepts Docling JSON")
        from .extraction import convert_document

        return convert_document(
            source,
            allow_url=args.allow_url,
            pdf_pipeline=args.pdf_pipeline,
            ocr=not args.no_ocr,
            max_pages=args.max_pages,
            max_input_bytes=args.max_input_bytes,
            **options,
        )
    if source == "-":
        payload = sys.stdin.buffer.read(args.max_input_bytes + 1)
    else:
        with Path(source).open("rb") as stream:
            payload = stream.read(args.max_input_bytes + 1)
    return export_json(
        payload, asset_root=args.asset_root, max_input_bytes=args.max_input_bytes, **options
    )


def _writable(path: Path, overwrite: bool) -> None:
    if path.is_symlink() or path.exists() and not overwrite:
        raise FileExistsError(path)
    if path.exists() and not path.is_file():
        raise ValueError("Output must be a file: " + str(path))


def _write(path: Path, value: str, overwrite: bool) -> None:
    _writable(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            from .capabilities import capabilities

            print(json.dumps(capabilities(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "serve":
            import uvicorn
            from .http import create_app

            uvicorn.run(
                create_app(max_input_bytes=args.max_input_bytes), host=args.host, port=args.port
            )
            return 0
        if args.command == "mcp":
            from .mcp import create_server

            create_server(root=args.root).run(transport="stdio")
            return 0
        if args.max_diagnostics < 0:
            raise ValueError("max_diagnostics must not be negative")
        if args.command == "batch":
            if (
                args.directory.resolve() == args.output_dir.resolve()
                or args.output_dir.resolve().is_relative_to(args.directory.resolve())
            ):
                raise ValueError("Batch output directory must be outside the input directory")
            if Path(args.pattern).is_absolute() or ".." in Path(args.pattern).parts:
                raise ValueError("Batch pattern must stay inside the input directory")
            inputs = [
                str(path) for path in sorted(args.directory.glob(args.pattern)) if path.is_file()
            ]
            if not inputs:
                raise ValueError("No input files matched")
            bundles = [
                args.output_dir / Path(source).relative_to(args.directory).with_suffix("")
                for source in inputs
            ]
        else:
            inputs = args.inputs
            if len(inputs) > 1 and args.bundle is None:
                raise ValueError("Multiple inputs require --bundle")
            if len(inputs) > 1 and (args.report is not None or args.assets_dir is not None):
                raise ValueError("Batch bundles carry their own reports and assets")
            if args.inputs.count("-") > 1:
                raise ValueError("Stdin can only be consumed once")
            bundles = [
                (args.bundle / Path(source).stem if len(inputs) > 1 else args.bundle)
                for source in inputs
            ]
            if args.report:
                _writable(args.report, args.force)
                if args.output is not None and args.report.resolve() == args.output.resolve():
                    raise ValueError("Report and source output must be different files")
                if inputs[0] != "-" and args.report.resolve() == Path(inputs[0]).resolve():
                    raise ValueError("Report must not replace its input")
            if args.output:
                _writable(args.output, args.force)
                if inputs[0] != "-" and args.output.resolve() == Path(inputs[0]).resolve():
                    raise ValueError("Output must not replace its input")
        resolved_bundles = [path.resolve() for path in bundles if path is not None]
        if len(set(resolved_bundles)) != len(resolved_bundles):
            raise ValueError("Input names collide at the bundle destination")
        if any(a != b and a.is_relative_to(b) for a in resolved_bundles for b in resolved_bundles):
            raise ValueError("Bundle destinations must not contain one another")
        for bundle in bundles:
            if bundle is not None and (bundle.is_symlink() or bundle.exists() and not args.force):
                raise FileExistsError(bundle)
        status = 0
        for source, bundle in zip(inputs, bundles):
            try:
                asset_prefix = "assets"
                if (
                    args.command == "convert"
                    and args.assets_dir is not None
                    and args.output is not None
                ):
                    try:
                        asset_prefix = (
                            args.assets_dir.resolve()
                            .relative_to(args.output.parent.resolve())
                            .as_posix()
                        )
                    except ValueError as error:
                        raise ValueError(
                            "Asset directory must be within the output document directory"
                        ) from error
                result = _result(source, args, asset_prefix=asset_prefix)
                if bundle is not None:
                    result.write_bundle(
                        bundle, overwrite=args.force, include_document=not args.no_source_snapshot
                    )
                else:
                    value = {
                        "carve": lambda: result.value,
                        "html": lambda: to_html(result.value),
                        "report-json": lambda: (
                            json.dumps(
                                result.to_dict(include_assets=True), ensure_ascii=False, indent=2
                            )
                            + "\n"
                        ),
                        "ast-json": lambda: (
                            json.dumps(result.ast, ensure_ascii=False, indent=2) + "\n"
                        ),
                    }[args.format]()
                    if args.output:
                        _write(args.output, value, args.force)
                    else:
                        sys.stdout.write(value)
                    if args.report:
                        _write(
                            args.report,
                            json.dumps(
                                result.to_dict(include_assets=True), ensure_ascii=False, indent=2
                            )
                            + "\n",
                            args.force,
                        )
                    asset_dir = args.assets_dir or (
                        args.output.parent / asset_prefix if args.output else None
                    )
                    if asset_dir is not None:
                        asset_dir.mkdir(parents=True, exist_ok=True)
                        for name, payload in result.assets.items():
                            destination = asset_dir / name
                            if destination.is_symlink():
                                raise ValueError("Asset output must not replace a symlink")
                            destination.write_bytes(payload)
                if result.total_diagnostics:
                    print(
                        f"{source}: {result.total_diagnostics} conversion diagnostic(s); inspect the report",
                        file=sys.stderr,
                    )
            except (ValueError, OSError) as error:
                status = 2 if isinstance(error, DoclingExportError) else max(status, 1)
                message: dict[str, Any] = {"input": source, "error": str(error)}
                if isinstance(error, DoclingExportError):
                    message["report"] = error.result.to_dict(include_assets=True)
                print(json.dumps(message, ensure_ascii=False), file=sys.stderr)
                if not args.keep_going:
                    return status
        return status
    except ImportError as error:
        print(
            f"Optional dependency is missing: {error}. Install docling-carve[extract], [http], or [mcp] for the requested interface.",
            file=sys.stderr,
        )
        return 1
    except (ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
