from pathlib import Path
import subprocess
import sys


def test_release_notes_select_matching_released_section(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    output = tmp_path / "notes.md"
    changelog.write_text(
        "# Changelog\n\n## 0.2.0 (unreleased)\n\nFuture.\n\n## 0.1.0 - 2026-10-04\n\n- Initial release.\n\n## 0.0.1\n\nOld.\n"
    )
    script = Path(__file__).resolve().parents[1] / "scripts/release_notes.py"
    result = subprocess.run(
        [sys.executable, str(script), "v0.1.0", str(output), "--changelog", str(changelog)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "- Initial release.\n"
    result = subprocess.run(
        [sys.executable, str(script), "v0.2.0", str(output), "--changelog", str(changelog)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0 and "must be released" in result.stderr
