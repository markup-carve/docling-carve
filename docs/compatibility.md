# Mapping and compatibility

The adapter uses Docling Core 2.99 or newer within major version 2 and the Carve 0.2 native writer (carve-rs `main`, pinned by commit in `Cargo.toml`). Optional extraction uses Docling 2.133 or newer within major version 2. MCP uses the version 2 SDK (`MCPServer`). CI checks installed wheels and real extraction separately.

| Docling content | Carve output | Review conditions |
| --- | --- | --- |
| Title and section heading | Heading levels 1 through 6 | Deeper levels are clamped |
| Text runs and inline groups | Paragraph with strong, emphasis, underline, strike, subscript, superscript, and links | Embedded blank lines and unsupported inline roles are normalized |
| Lists and nested list groups | Ordered or unordered lists | Inconsistent numeric markers and malformed groups need review |
| Code | Fenced code with known language | Captions become code block captions |
| Formula | Math block | Empty formulas are omitted with a diagnostic |
| Tables | Rectangular grid with row and column spans | Invalid geometry is refused; rich block cells are flattened |
| Table and image captions | Table and image paragraph captions | Multiline captions are normalized |
| Pictures | Content-addressed PNG assets | Missing pixels retain caption text with a diagnostic |
| Item provenance | AST paths, Docling references, page geometry | Ambiguous cell page assignment is reported |
| Other groups and roles | Flattened content when available | Role loss is reported |
| Metadata, comments, footnote associations | Report and original snapshot | No source representation is claimed |

An empty merged table origin uses a visible `[empty]` placeholder to preserve geometry. Completely blank rows that have no Carve source spelling are omitted with a diagnostic. Row and column header flags map to Carve header cells; the source format does not retain every Docling header role distinction.

Diagnostics are conversion findings. `total_diagnostics` counts all findings even when `max_diagnostics` truncates their entries. `truncated` makes that distinction explicit. Strict mode uses the total count, so setting the retention limit to zero cannot bypass refusal.

The AST is an AST 2.0 tree (`astVersion` `"2.0"`) and contains converted content. It is separate from the original Docling snapshot and from an AST parsed back from the emitted source. Downstream tools should use the report's provenance paths against the converted AST. Paths follow the 2.0 tree: list items are `/children/N` of their list, and a table cell is `/children/G/children/R/children/C`, where group `G` is the `table_head` (the leading all-header rows) or the `table_body`. Original layout, excluded layers, document metadata, and extraction uncertainty require the snapshot or the original file.

This package exports Carve source and can run behind consumers written in JavaScript, PHP, Rust, or other languages. It does not add Docling or Python dependencies to those consumers. Its HTTP and MCP contracts provide access to the optional extraction pipeline without embedding it in a language binding.
