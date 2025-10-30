from style_variant_builder.prune import CSLPruner, _tag

EXAMPLE_XML = """<?xml version="1.0"?>
<style xmlns="http://purl.org/net/xbiblio/csl">
  <macro name="used-macro"><text value="used"/></macro>
  <macro name="unused-macro"><text value="unused"/></macro>
  <citation>
    <layout>
      <text macro="used-macro"/>
    </layout>
  </citation>
</style>
"""

EXAMPLE_WITH_XML_MODEL = """<?xml version="1.0"?>
<?xml-model href="http://example.com/schema.rng" type="application/xml"?>
<style xmlns="http://purl.org/net/xbiblio/csl">
  <macro name="test-macro"><text value="test"/></macro>
  <citation>
    <layout>
      <text macro="test-macro"/>
    </layout>
  </citation>
</style>
"""


def test_prune_removes_unused_macros(tmp_path):
    xml_path = tmp_path / "test.csl"
    xml_path.write_text(EXAMPLE_XML)
    pruner = CSLPruner(xml_path, xml_path)
    pruner.parse_xml()
    pruner.collect_macro_definitions()
    pruner.build_used_macros()
    pruner.prune_macros()
    assert pruner.root is not None
    macros = [m.get("name") for m in pruner.root.findall(_tag("macro"))]
    assert "used-macro" in macros
    assert "unused-macro" not in macros


def test_prune_keeps_used_macros(tmp_path):
    xml_path = tmp_path / "test.csl"
    xml_path.write_text(EXAMPLE_XML)
    pruner = CSLPruner(xml_path, xml_path)
    pruner.parse_xml()
    pruner.collect_macro_definitions()
    pruner.build_used_macros()
    pruner.prune_macros()
    assert pruner.root is not None
    macros = [m.get("name") for m in pruner.root.findall(_tag("macro"))]
    assert "used-macro" in macros


def test_xml_model_pi_excluded_from_output(tmp_path):
    """Test that xml-model processing instructions are excluded from saved output."""
    input_path = tmp_path / "input.csl"
    output_path = tmp_path / "output.csl"
    input_path.write_text(EXAMPLE_WITH_XML_MODEL)

    pruner = CSLPruner(input_path, output_path)
    pruner.parse_xml()
    pruner.prune_macros()
    pruner.save()

    output_content = output_path.read_text()
    # Verify xml-model PI is not in output
    assert "<?xml-model" not in output_content
    # Verify the actual content is preserved
    assert "<macro" in output_content
    assert "<citation>" in output_content
