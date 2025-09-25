import shutil
import subprocess
import sys


def test_cli_main_builds_and_errors(tmp_path):
    # Setup: create a minimal template and diff
    templates = tmp_path / "templates"
    diffs = tmp_path / "diffs"
    output = tmp_path / "output"
    templates.mkdir()
    diffs.mkdir()
    output.mkdir()
    template = templates / "foo-template.csl"
    template.write_text(
        """<style xmlns='http://purl.org/net/xbiblio/csl'><info/></style>\n"""
    )
    # No diffs present, so build should still succeed (no variants)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "style_variant_builder.build",
            "--templates-path",
            str(templates),
            "--diffs-path",
            str(diffs),
            "--output-path",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "Processing style family: " in combined
    # Now test error: remove templates
    shutil.rmtree(templates)
    result2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "style_variant_builder.build",
            "--templates-path",
            str(templates),
            "--diffs-path",
            str(diffs),
            "--output-path",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result2.returncode != 0
    combined2 = result2.stdout + result2.stderr
    assert "No template files found" in combined2
