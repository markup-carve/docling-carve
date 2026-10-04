"""Check an installed wheel without importing the working tree."""

import json
from importlib.metadata import version
from pathlib import Path
import sys
import zipfile

import docling_carve
from docling_core.types.doc import DoclingDocument, DocItemLabel

assert "site-packages" in str(Path(docling_carve.__file__).resolve())
assert docling_carve.__version__ == version("docling-carve")
assert docling_carve.ENGINE_VERSION == "0.1.7"
doc = DoclingDocument(name="wheel")
doc.add_heading("Installed wheel", level=2)
doc.add_text(label=DocItemLabel.PARAGRAPH, text="Contract check.")
result = docling_carve.export_json(doc.export_to_dict(), strict=True)
assert "Installed wheel" in result.value and not result.total_diagnostics
assert json.loads(docling_carve._native.parse_json(result.value))["type"] == "document"
assert docling_carve._native.to_carve(result.value) == result.value
assert docling_carve.CarveSerializerProvider().get_serializer(doc).serialize().text == result.value
schema = Path(docling_carve.__file__).parent / "schemas" / "report-v1.json"
assert json.loads(schema.read_text())["title"] == "Docling Carve export report"
for argument in sys.argv[1:]:
    with zipfile.ZipFile(argument) as wheel:
        names = wheel.namelist()
        assert any(name.endswith("py.typed") for name in names)
        assert any(name.endswith("report-v1.json") for name in names)
        assert not any(name.startswith(("tests/", "docs/", ".github/")) for name in names)
print("Installed wheel contract passed")
