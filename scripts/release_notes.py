"""Extract the released changelog section for a matching version tag."""

import argparse
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument("tag")
parser.add_argument("output", type=Path)
parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
args = parser.parse_args()
if not re.fullmatch(r"v\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)", args.tag):
    parser.error("Expected a version tag")
version = args.tag[1:]
sections = re.split(r"(?m)^## ", args.changelog.read_text(encoding="utf-8"))
for section in sections[1:]:
    heading, _, body = section.partition("\n")
    if re.match(r"\[?" + re.escape(version) + r"\]?(?:\s|$)", heading):
        if "unreleased" in heading.lower() or not body.strip():
            parser.error("Changelog section must be released and nonempty")
        args.output.write_text(body.strip() + "\n", encoding="utf-8")
        break
else:
    parser.error("No changelog section matches the tag")
