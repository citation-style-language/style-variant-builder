from style_variant_builder.prune import NS, CSLPruner

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


def test_prune_removes_unused_macros(tmp_path):
    xml_path = tmp_path / "test.csl"
    xml_path.write_text(EXAMPLE_XML)
    pruner = CSLPruner(xml_path, xml_path)
    pruner.parse_xml()
    pruner.collect_macro_definitions()
    pruner.build_used_macros()
    pruner.prune_macros()
    assert pruner.root is not None
    macros = [m.get("name") for m in pruner.root.findall(f"{NS}macro")]
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
    macros = [m.get("name") for m in pruner.root.findall(f"{NS}macro")]
    assert "used-macro" in macros
