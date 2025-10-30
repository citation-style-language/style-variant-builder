from style_variant_builder.build import CSLBuilder


def test_apply_patch_success(tmp_path):
    # Create a simple template and diff that adds a macro
    template = tmp_path / "template.csl"
    template.write_text("""<style><info/><macro name='foo'/></style>\n""")
    diff = tmp_path / "patch.diff"
    diff.write_text(
        """--- a/template.csl\n+++ b/template.csl\n@@ -1 +1 @@\n-<style><info/><macro name='foo'/></style>\n+<style><info/><macro name='foo'/><macro name='bar'/></style>\n"""
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Test the static worker method directly
    diff_name, success, message = CSLBuilder._process_single_diff(
        diff_path=diff,
        template_path=template,
        target_output_dir=output_dir,
        development_dir=None,
        export_development=False,
    )

    assert success is True
    assert diff_name == "patch.diff"
    output_file = output_dir / "patch.csl"
    assert output_file.exists()
    patched = output_file.read_text()
    # Check that the new macro was added
    assert 'name="bar"' in patched
    # Check that the notice comment was added by the pruner
    assert "Style Variant Builder" in patched


def test_apply_patch_failure(tmp_path):
    # Create a template and a broken diff
    template = tmp_path / "template.csl"
    template.write_text("<style><info/></style>\n")
    diff = tmp_path / "broken.diff"
    diff.write_text("this is not a valid diff")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Test the static worker method directly
    diff_name, success, message = CSLBuilder._process_single_diff(
        diff_path=diff,
        template_path=template,
        target_output_dir=output_dir,
        development_dir=None,
        export_development=False,
    )

    assert success is False
    assert "Failed to apply patch" in message
