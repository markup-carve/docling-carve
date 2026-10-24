from pathlib import Path
import subprocess
import sys


def test_release_notes_select_matching_released_section(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    output = tmp_path / "notes.md"
    changelog.write_text(
        "# Changelog\n\n## 0.2.0 (unreleased)\n\nFuture.\n\n## 0.1.0 - 2026-10-04\n\n- Initial release: Ł.\n\n## 0.0.1\n\nOld.\n",
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "scripts/release_notes.py"
    result = subprocess.run(
        [sys.executable, str(script), "0.1.0", str(output), "--changelog", str(changelog)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == "- Initial release: Ł.\n"
    result = subprocess.run(
        [sys.executable, str(script), "0.2.0", str(output), "--changelog", str(changelog)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0 and "must be released" in result.stderr
    result = subprocess.run(
        [sys.executable, str(script), "v0.1.0", str(output), "--changelog", str(changelog)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0 and "Expected a version tag" in result.stderr


def test_check_version_accepts_bare_tag_and_rejects_prefix():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts/check_version.py"
    for tag, expected in [("0.1.0", 0), ("v0.1.0", 1)]:
        result = subprocess.run(
            [sys.executable, str(script), tag], cwd=root, capture_output=True, text=True, timeout=10
        )
        assert result.returncode == expected, result.stderr
