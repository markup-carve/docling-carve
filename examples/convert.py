from docling_core.types.doc import DoclingDocument, DocItemLabel
from docling_carve import export_docling

document = DoclingDocument(name="example")
document.add_heading("Quarterly report", level=1)
document.add_text(label=DocItemLabel.PARAGRAPH, text="Reviewed document content.")
result = export_docling(document)
result.write_bundle("example-bundle")
print(result.value)
