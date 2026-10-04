"""Load the report schema distributed with the package."""

from importlib.resources import files
import json


def report_schema() -> dict:
    return json.loads(files("docling_carve").joinpath("schemas/report-v1.json").read_text())
