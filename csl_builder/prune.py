"""
Remove unused macros from a CSL file.
"""

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

logging.basicConfig(level=logging.INFO, format="%(message)s")
NS = "{http://purl.org/net/xbiblio/csl}"


@dataclass(slots=True)
class CSLPruner:
    input_path: Path
    output_path: Path
    tree: etree._ElementTree | None = field(default=None, init=False)
    root: etree._Element | None = field(default=None, init=False)
    macro_defs: dict[str, etree._Element] = field(
        default_factory=dict, init=False
    )
    parent_map: dict[etree._Element, etree._Element] = field(
        default_factory=dict, init=False
    )
    modified: bool = field(
        default=False, init=False
    )  # Track whether changes have been made

    def parse_xml(self) -> None:
        try:
            self.tree = etree.parse(self.input_path)
            if self.tree is None:
                raise ValueError("Parsed XML tree is None.")
            self.root = self.tree.getroot()
        except Exception as e:
            logging.error(
                "Unable to parse the XML file. Please ensure the file is valid XML.",
                exc_info=True,
            )
            raise e
        if self.root is None:
            msg = "The XML file appears to be empty or malformed. Please verify its contents."
            logging.error(msg)
            raise ValueError(msg)
        self.build_parent_map()
        self.collect_macro_definitions()

    def build_parent_map(self) -> None:
        """Build a mapping from each node to its parent for removal operations."""
        if self.root is None:
            msg = "XML structure missing: the root element could not be found. Please check the input file."
            logging.error(msg)
            raise ValueError(msg)
        self.parent_map = {}
        for element in self.root.iter():
            for child in element:
                self.parent_map[child] = element

    def collect_macro_definitions(self) -> None:
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

    def gather_macro_refs(self, element: etree._Element) -> set:
        """Recursively collect macro names to which the element refers."""
        refs = set()
        macro_attr = element.attrib.get("macro")
        if macro_attr:
            refs.add(macro_attr)
        for child in element:
            refs.update(self.gather_macro_refs(child))
        return refs

    def build_used_macros(self) -> set:
        if self.root is None:
            msg = "Root is None. Ensure parse_xml() is called successfully."
            logging.error(msg)
            raise ValueError(msg)
        used_macros = set()

        def add_macro_and_deps(macro_name: str) -> None:
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

    def prune_macros(self) -> None:
        total_removed = []
        while True:
            used_macros = self.build_used_macros()
            removed = []
            for name, macro in list(self.macro_defs.items()):
                if name not in used_macros:
                    parent = self.parent_map.get(macro, macro.getparent())
                    if parent is not None:
                        parent.remove(macro)
                        removed.append(name)
                        logging.debug(f"Removed macro: {name}")
            if removed:
                self.modified = True
                total_removed.extend(removed)
                self.collect_macro_definitions()
                self.build_parent_map()
            else:
                logging.debug("No unused macros found.")
                break
        if total_removed:
            logging.info(
                f"Removed a total of {len(total_removed)} unused macros."
            )
        else:
            logging.info("No macros pruned.")

    def normalize_xml_content(self, xml_data: bytes) -> bytes:
        """Revert Python changes to XML content."""
        text = xml_data.decode("utf-8")
        text = re.sub(
            r"<\?xml version='1\.0' encoding='utf-8'\?>",
            '<?xml version="1.0" encoding="utf-8"?>',
            text,
        )
        text = text.replace("———", "&#8212;&#8212;&#8212;")
        return text.encode("utf-8")

    def save(self) -> None:
        if self.tree is not None:
            try:
                xml_data = etree.tostring(
                    self.tree,
                    encoding="utf-8",
                    xml_declaration=True,
                    pretty_print=True,
                )
                xml_data = self.normalize_xml_content(xml_data)
                self.output_path.write_bytes(xml_data)
            except Exception as e:
                logging.error(
                    "Failed to save the pruned XML file. Please ensure the output path is valid and writable.",
                    exc_info=True,
                )
                raise e
        else:
            msg = (
                "Cannot save file because the XML was not successfully loaded."
            )
            logging.error(msg)
            raise ValueError(msg)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_path", type=Path, help="Path to the input CSL file."
    )
    parser.add_argument(
        "output_path", type=Path, help="Path to the output pruned CSL file."
    )
    args: argparse.Namespace = parser.parse_args()

    pruner = CSLPruner(args.input_path, args.output_path)
    try:
        pruner.parse_xml()
        pruner.prune_macros()
        pruner.save()
        if pruner.modified:
            logging.info(f"Pruned {args.output_path}")
        else:
            logging.info(f"No macros pruned in {args.input_path}")
        return 0
    except Exception:
        logging.error("An error occurred during processing.", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
