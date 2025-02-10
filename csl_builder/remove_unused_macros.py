import argparse
import logging
from lxml import etree as ET
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)

NAMESPACE = "http://purl.org/net/xbiblio/csl"
NS = f"{{{NAMESPACE}}}"


class CSLPruner:
    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path
        self.tree = None
        self.root = None
        self.macro_defs: dict[str, ET._Element] = {}
        self.parent_map: dict[ET._Element, ET._Element] = {}

    def parse_xml(self):
        try:
            self.tree = ET.parse(self.input_path)
            self.root = self.tree.getroot()
        except Exception as e:
            logging.error("Unable to parse the XML file. Please ensure the file is valid XML.", exc_info=True)
            raise e

        if self.root is None:
            msg = "The XML file appears to be empty or malformed. Please verify its contents."
            logging.error(msg)
            raise ValueError(msg)
        self.build_parent_map()
        self.collect_macro_definitions()

    def build_parent_map(self):
        """Build a mapping from each node to its parent for removal operations."""
        if self.root is None:
            msg = "XML structure missing: the root element could not be found. Please check the input file."
            logging.error(msg)
            raise ValueError(msg)
        self.parent_map = {}
        # lxml supports getparent(), so we can iterate over all elements.
        for element in self.root.iter():
            for child in element:
                self.parent_map[child] = element

    def collect_macro_definitions(self):
        """Collect <macro> elements keyed on their 'name' attribute."""
        if self.root is None:
            msg = "Cannot collect macros because the XML root is missing. Ensure the file has valid XML content."
            logging.error(msg)
            raise ValueError(msg)
        self.macro_defs = {}
        for elem in self.root.iter(f"{NS}macro"):
            name = elem.attrib.get("name")
            if name:
                self.macro_defs[name] = elem

    def gather_macro_refs(self, element: ET._Element) -> set:
        """Recursively collect macro names to which the element refers."""
        refs = set()
        macro_attr = element.attrib.get("macro")
        if macro_attr:
            refs.add(macro_attr)
        for child in element:
            refs.update(self.gather_macro_refs(child))
        return refs

    def build_used_macros(self):
        if self.root is None:
            msg = "Root is None. Ensure parse_xml() is called successfully."
            logging.error(msg)
            raise ValueError(msg)
        used_macros = set()

        def add_macro_and_deps(macro_name: str):
            if macro_name in used_macros:
                return
            used_macros.add(macro_name)
            macro = self.macro_defs.get(macro_name)
            if macro is not None:
                refs = self.gather_macro_refs(macro)
                for ref in refs:
                    add_macro_and_deps(ref)

        # Entry points: <citation> and <bibliography>
        entry_tags = [f"{NS}citation", f"{NS}bibliography"]
        entry_macro_refs = set()
        for tag in entry_tags:
            for entry in self.root.iter(tag):
                entry_macro_refs.update(self.gather_macro_refs(entry))
        # Also, check the whole document
        entry_macro_refs.update(self.gather_macro_refs(self.root))
        for ref in entry_macro_refs:
            add_macro_and_deps(ref)
        return used_macros

    def prune_macros(self):
        total_removed = []
        while True:
            used_macros = self.build_used_macros()
            removed = []
            # Remove macros no longer referenced
            for name, macro in list(self.macro_defs.items()):
                if name not in used_macros:
                    parent = self.parent_map.get(macro, macro.getparent())
                    if parent is not None:
                        parent.remove(macro)
                        removed.append(name)
                        logging.info(f"Removed macro: {name}")
            if removed:
                total_removed.extend(removed)
                logging.info(f"Removed {len(removed)} unused macros on this pass.")
                # Rebuild the definitions and parent map since the tree has changed
                self.collect_macro_definitions()
                self.build_parent_map()
            else:
                logging.info("No unused macros found on this pass.")
                break

    def save(self):
        if self.tree is not None:
            try:
                self.tree.write(self.output_path, encoding="utf-8", xml_declaration=True, pretty_print=True)
            except Exception as e:
                logging.error("Failed to save the pruned XML file. Please ensure the output path is valid and writable.", exc_info=True)
                raise e
        else:
            msg = "Cannot save file because the XML data was not successfully loaded. Verify your input file and try again."
            logging.error(msg)
            raise ValueError(msg)


def main():
    parser = argparse.ArgumentParser(
        description="Remove unused macros from a CSL file."
    )
    parser.add_argument("input_path", type=str, help="Path to the input CSL file.")
    parser.add_argument(
        "output_path", type=str, help="Path to the output pruned CSL file."
    )
    args = parser.parse_args()

    pruner = CSLPruner(args.input_path, args.output_path)
    try:
        pruner.parse_xml()
        pruner.prune_macros()
        pruner.save()
        logging.info(f"Pruned file written to {args.output_path}")
        return 0
    except Exception as e:
        logging.error("An error occurred during processing.", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
