import os
import subprocess
import sys
from pathlib import Path

from lxml import etree


def test_full_build_outputs_are_valid(tmp_path):
    # Copy templates, diffs, etc. to tmp_path for isolation
    import shutil

    root = Path(__file__).parent.parent
    for d in ["templates", "diffs"]:
        shutil.copytree(root / d, tmp_path / d)
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    # Run the build as in the Makefile
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "style_variant_builder.build",
            "--templates-path",
            str(tmp_path / "templates"),
            "--diffs-path",
            str(tmp_path / "diffs"),
            "--output-path",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Build failed: {result.stderr or result.stdout}"
    # Recursively check all .csl files in output for XML validity
    broken = []
    for dirpath, _, filenames in os.walk(output_dir):
        for fn in filenames:
            if fn.endswith(".csl"):
                fpath = Path(dirpath) / fn
                try:
                    etree.parse(str(fpath))
                except Exception as e:
                    broken.append((str(fpath), str(e)))
    assert not broken, f"Broken output styles: {broken}"
