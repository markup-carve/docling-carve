"""Reject a release tag or native package with a different distribution version."""

from pathlib import Path
import re
import sys
import subprocess
import tempfile


def version(path):
    return re.search(r'^version\s*=\s*"([^"]+)"', Path(path).read_text(), re.MULTILINE)[1]


distribution = version("pyproject.toml")
assert version("Cargo.toml") == distribution
assert f'=={distribution}"' in Path("Dockerfile").read_text()
if sys.argv[1].startswith("v"):
    assert sys.argv[1] == "v" + distribution
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("release_notes.py")),
                sys.argv[1],
                str(Path(directory) / "notes.md"),
            ],
            check=True,
        )
assert 'panic = "abort"' not in Path("Cargo.toml").read_text()
print("Version and unwind guards passed")
