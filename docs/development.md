# Development and release

Build the installed package before running tests:

```sh
python -m venv .venv
. .venv/bin/activate
pip install maturin
maturin develop --release
pip install -e '.[dev,http,mcp]'
pytest -q
ruff check python tests scripts examples
cargo fmt --check
```

Extraction tests skip when Docling is absent. Install `.[extract]` to run the HTML, Office, and native PDF tests. These fixtures do not require OCR model downloads. Standard PDF OCR remains dependent on Docling's model downloads and platform support.

CI runs Python 3.10, 3.12, and 3.14, checks the report schema and installed-wheel contract, and exercises the optional HTTP and MCP interfaces. A separate job installs CPU Torch and Docling for real extraction tests. Release builds cover Linux glibc and musl on x86_64 and aarch64, macOS x86_64 and arm64, and Windows x86_64. Every platform installs its produced wheel and runs the same contract gate before publishing.

The release workflow builds and validates an sdist too. Cargo dependency resolution is locked. Distribution and native versions must match. The wheel contains the Python type marker, native stubs, and report schema, while source distributions exclude private scratch files and repository test infrastructure.

To release, update `pyproject.toml`, `Cargo.toml`, the container's package version, and `CHANGELOG.md`. Mark the matching changelog section as released before tagging. Push a matching `vX.Y.Z` tag only after the release commit has merged. Release gates validate that section before publication; GitHub notes contain only its entries. Publication requires the repository's `pypi` environment and a matching PyPI trusted publisher configured for `release.yml`. Workflow dispatch builds artifacts without publishing. This repository has not yet published a package.

The initial implementation came from the Docling pilot in `carve-py`. The standalone package owns the adapter, interfaces, schemas, fixtures, and native wrapper. `carve-py` retains only its general AST-writing API. The native engine remains the published `carve-lang` Rust crate.
