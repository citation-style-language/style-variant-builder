from pathlib import Path

from style_variant_builder.build import CSLBuilder


def test_apply_patch_success(tmp_path):
    # Create a simple template and diff
    template = tmp_path / "template.csl"
    template.write_text("""<style><info/><macro name='foo'/></style>\n""")
    diff = tmp_path / "patch.diff"
    diff.write_text(
        """--- a/template.csl\n+++ b/template.csl\n@@ -1 +1,2 @@\n <style><info/><macro name='foo'/></style>\n+<!-- Added line -->\n"""
    )
    builder = CSLBuilder(
        templates_dir=tmp_path,
        diffs_dir=tmp_path,
        output_dir=tmp_path,
        development_dir=tmp_path,
        style_family="template",
        export_development=False,
        generate_diffs=False,
        group_by_family=False,
    )
    result = builder._apply_patch(template, diff)
    assert result is not None
    patched = Path(result).read_text()
    assert "Added line" in patched


def test_apply_patch_failure(tmp_path):
    # Create a template and a broken diff
    template = tmp_path / "template.csl"
    template.write_text("<style><info/></style>\n")
    diff = tmp_path / "broken.diff"
    diff.write_text("this is not a valid diff")
    builder = CSLBuilder(
        templates_dir=tmp_path,
        diffs_dir=tmp_path,
        output_dir=tmp_path,
        development_dir=tmp_path,
        style_family="template",
        export_development=False,
        generate_diffs=False,
        group_by_family=False,
    )
    result = builder._apply_patch(template, diff)
    assert result is None
