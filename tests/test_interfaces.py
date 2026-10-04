import asyncio
import json
import subprocess
import sys

import pytest
from docling_core.types.doc import DoclingDocument, DocItemLabel, ImageRef
from PIL import Image
from docling_carve import CarveDocSerializer, CarveSerializerProvider, export_docling, export_json
from docling_carve import _native


def example():
    doc = DoclingDocument(name="interfaces")
    doc.add_heading("Shared input", level=2)
    doc.add_text(label=DocItemLabel.TEXT, text="Plain *literal* content.")
    return doc


def cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "docling_carve", *map(str, args)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_installed_cli_stdin_reports_bundles_and_exit_codes(tmp_path):
    doc = example()
    payload = json.dumps(doc.export_to_dict())
    response = cli("convert", "-", "--format", "report-json", stdin=payload)
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout)["value"] == export_docling(doc).value
    source = tmp_path / "input.json"
    source.write_text(payload)
    result = cli("convert", source, "--bundle", tmp_path / "bundle")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "bundle/document.crv").exists()
    assert cli("convert", source, "--bundle", tmp_path / "bundle").returncode == 1
    assert cli("convert", source, "--bundle", tmp_path / "bundle", "--force").returncode == 0
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="role fallback")
    result = cli("convert", "-", "--strict", stdin=json.dumps(doc.export_to_dict()))
    assert result.returncode == 2 and not result.stdout
    assert json.loads(result.stderr)["report"]["total_diagnostics"] > 0
    assert cli("convert", "-", stdin="not JSON").returncode == 1


def test_batch_nested_paths_and_failed_input_keep_going(tmp_path):
    inputs = tmp_path / "inputs"
    (inputs / "nested").mkdir(parents=True)
    value = json.dumps(example().export_to_dict())
    (inputs / "one.json").write_text(value)
    (inputs / "nested/two.json").write_text(value)
    output = tmp_path / "out"
    result = cli("batch", inputs, "--output-dir", output)
    assert result.returncode == 0, result.stderr
    assert (output / "one/document.crv").exists()
    assert (output / "nested/two/document.crv").exists()
    (inputs / "bad.json").write_text("{}")
    result = cli("batch", inputs, "--output-dir", tmp_path / "out2", "--keep-going")
    assert result.returncode == 1
    assert (tmp_path / "out2/one/document.crv").exists()
    assert cli("batch", inputs, "--output-dir", inputs / "out").returncode == 1


def test_serializer_is_a_real_docling_provider_and_preserves_spans():
    doc = example()
    serializer = CarveSerializerProvider(strict=True).get_serializer(doc)
    assert isinstance(serializer, CarveDocSerializer)
    result = serializer.serialize()
    assert result.text == export_docling(doc).value
    assert {item.self_ref for item in result.get_unique_doc_items()} == {"#/texts/0", "#/texts/1"}
    assert (
        serializer.serialize(item=doc.texts[1]).text == export_docling(doc, root=doc.texts[1]).value
    )
    assert "<strong>literal</strong>" in _native.to_html(serializer.serialize_bold("literal"))


def test_external_images_require_an_explicit_contained_root(tmp_path):
    image = tmp_path / "image.png"
    Image.new("RGB", (2, 2)).save(image)
    doc = DoclingDocument(name="local")
    doc.add_picture(image=ImageRef.from_pil(Image.new("RGB", (2, 2)), dpi=72))
    payload = doc.export_to_dict()
    payload["pictures"][0]["image"]["uri"] = image.as_uri()
    with pytest.raises(ValueError, match="asset_root"):
        export_json(payload)
    assert export_json(payload, asset_root=tmp_path).assets
    sibling = tmp_path / "other"
    sibling.mkdir()
    with pytest.raises(ValueError, match="escapes"):
        export_json(payload, asset_root=sibling)
    payload["pictures"][0]["image"]["uri"] = "https://example.com/image.png"
    with pytest.raises(ValueError, match="remote"):
        export_json(payload, asset_root=tmp_path)


def test_http_parity_auth_limits_validation_and_strict_failure():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from docling_carve.http import create_app

    client = TestClient(create_app(token="secret"))
    assert client.get("/v1/schema").status_code == 401
    assert (
        client.get("/v1/schema", headers={"Authorization": "Bearer secret"}).json()["title"]
        == "Docling Carve export report"
    )
    doc = example()
    envelope = {"document": doc.export_to_dict()}
    assert client.post("/v1/convert", json=envelope).status_code == 401
    headers = {"Authorization": "Bearer secret"}
    response = client.post("/v1/convert", json=envelope, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == export_json(doc.export_to_dict()).to_dict(include_assets=True)
    assert client.post("/v1/convert", json={"document": True}, headers=headers).status_code == 400
    assert (
        client.post(
            "/v1/convert", json={**envelope, "options": {"asset_dir": "/tmp"}}, headers=headers
        ).status_code
        == 400
    )
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="fallback")
    response = client.post(
        "/v1/convert",
        json={"document": doc.export_to_dict(), "options": {"strict": True}},
        headers=headers,
    )
    assert (
        response.status_code == 422
        and response.json()["detail"]["report"]["total_diagnostics"] == 1
    )
    small = TestClient(create_app(max_input_bytes=10, token="secret"))
    assert small.post("/v1/convert", json=envelope, headers=headers).status_code == 413


def test_mcp_protocol_round_trip_uses_the_same_report():
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "docling_carve", "mcp"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resources = await session.list_resources()
                assert any(
                    str(resource.uri) == "docling-carve://schema/report-v1"
                    for resource in resources.resources
                )
                schema = await session.read_resource("docling-carve://schema/report-v1")
                assert json.loads(schema.contents[0].text)["title"] == "Docling Carve export report"
                tools = await session.list_tools()
                assert {"docling_to_carve", "docling_extract", "docling_carve_capabilities"} <= {
                    tool.name for tool in tools.tools
                }
                result = await session.call_tool(
                    "docling_to_carve", {"document": example().export_to_dict()}
                )
                assert not result.is_error
                assert result.structured_content == export_json(example().export_to_dict()).to_dict(
                    include_assets=True
                )
                diagnostic_doc = example()
                diagnostic_doc.add_text(label=DocItemLabel.PAGE_HEADER, text="review")
                strict = await session.call_tool(
                    "docling_to_carve",
                    {"document": diagnostic_doc.export_to_dict(), "strict": True},
                )
                assert strict.is_error and strict.structured_content["total_diagnostics"] == 1
                refused = await session.call_tool("docling_extract", {"path": "/etc/passwd"})
                assert refused.is_error

    asyncio.run(run())


def test_bundle_overwrite_does_not_delete_unmanaged_files(tmp_path):
    result = export_docling(example())
    target = result.write_bundle(tmp_path / "bundle")
    (target / "personal.txt").write_text("preserve")
    with pytest.raises(ValueError, match="outside"):
        result.write_bundle(target, overwrite=True)
    assert (target / "personal.txt").read_text() == "preserve"
