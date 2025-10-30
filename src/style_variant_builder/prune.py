"""
Remove unused macros from a CSL file.
"""

import argparse
import logging
import re
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

logging.basicConfig(level=logging.INFO, format="%(message)s")

NSMAP = {"csl": "http://purl.org/net/xbiblio/csl"}


def _tag(local_name: str) -> str:
    """Helper to construct fully-qualified tag names."""
    return f"{{{NSMAP['csl']}}}{local_name}"


@dataclass(slots=True)
class CSLPruner:
    input_path: Path
    output_path: Path
    tree: etree._ElementTree | None = field(default=None, init=False)
    root: etree._Element | None = field(default=None, init=False)
    macro_defs: dict[str, etree._Element] = field(
        default_factory=dict, init=False
    )
    modified: bool = field(
        default=False, init=False
    )  # Track whether changes have been made
    notice_comment: str | None = field(default=None, init=False)

    def parse_xml(self) -> None:
        try:
            parser = etree.XMLParser(
                remove_blank_text=True, resolve_entities=False, no_network=True
            )
            self.tree = etree.parse(self.input_path, parser=parser)
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
        self.collect_macro_definitions()

    def collect_macro_definitions(self) -> None:
        """Collect <macro> elements keyed on their 'name' attribute."""
        if self.root is None:
            msg = "Cannot collect macros because the XML root is missing. Ensure the file has valid XML content."
            logging.error(msg)
            raise ValueError(msg)
        self.macro_defs = {}
        for elem in self.root.iter(_tag("macro")):
            if name := elem.attrib.get("name"):
                self.macro_defs[name] = elem

    def flatten_layout_macros(self) -> int:
        """Flatten layout macro wrappers.

        If a <layout> has exactly one child, and that child is a <text> element
        with only a macro attribute (no other attributes), replace that child
        with the body (children) of the referenced macro. This simplifies the
        tree so that wrapper macros can be pruned subsequently.

        Returns the number of <layout> nodes updated.
        """
        if self.root is None:
            msg = "Root is None. Ensure parse_xml() is called successfully."
            logging.error(msg)
            raise ValueError(msg)

        updated = 0
        for layout in self.root.iter(_tag("layout")):
            # Consider only element children (lxml iteration skips comments/text by default)
            children = [ch for ch in layout if isinstance(ch.tag, str)]
            if len(children) != 1:
                continue
            only_child = children[0]
            if only_child.tag != _tag("text"):
                continue

            # Require a pure macro call to avoid changing semantics if other attributes exist
            # Build a concrete dict[str, str] of attributes for type safety
            attrs: dict[str, str] = {
                str(k): str(v) for k, v in only_child.attrib.items()
            }
            # Ensure the attribute is a string (lxml can expose AnyStr)
            if not isinstance(macro_attr := attrs.get("macro"), str):
                continue
            if not macro_attr or len(attrs) != 1:
                continue

            if (macro_def := self.macro_defs.get(macro_attr)) is None:
                # Unknown macro; skip
                continue

            # Replace the <text macro="..."/> with the macro's child nodes
            for ch in list(layout):
                layout.remove(ch)
            for sub in list(macro_def):
                layout.append(deepcopy(sub))

            updated += 1

        if updated:
            self.modified = True
            # Tree structure changed; rebuild macro definitions for subsequent operations
            self.collect_macro_definitions()
        return updated

    def gather_macro_refs(self, element: etree._Element) -> set[str]:
        """Recursively collect macro names to which the element refers."""
        refs: set[str] = set()
        if macro_attr := element.attrib.get("macro"):
            refs.add(macro_attr)
        for child in element:
            refs.update(self.gather_macro_refs(child))
        return refs

    def build_used_macros(self) -> set[str]:
        if self.root is None:
            msg = "Root is None. Ensure parse_xml() is called successfully."
            logging.error(msg)
            raise ValueError(msg)
        used_macros: set[str] = set()

        def add_macro_and_deps(macro_name: str) -> None:
            if macro_name in used_macros:
                return
            used_macros.add(macro_name)
            if (macro := self.macro_defs.get(macro_name)) is not None:
                refs = self.gather_macro_refs(macro)
                for ref in refs:
                    add_macro_and_deps(ref)

        # Entry points: <citation> and <bibliography>
        entry_tags = [_tag("citation"), _tag("bibliography")]
        entry_macro_refs = {
            ref
            for tag in entry_tags
            for entry in self.root.iter(tag)
            for ref in self.gather_macro_refs(entry)
        }
        entry_macro_refs.update(self.gather_macro_refs(self.root))
        for ref in entry_macro_refs:
            add_macro_and_deps(ref)
        return used_macros

    def prune_macros(self) -> None:
        total_removed_count = 0
        while True:
            used_macros = self.build_used_macros()
            removed = []
            for name, macro in list(self.macro_defs.items()):
                if name not in used_macros:
                    if (parent := macro.getparent()) is not None:
                        parent.remove(macro)
                        removed.append(name)
                        logging.debug(f"Removed macro: {name}")
            if removed:
                self.modified = True
                total_removed_count += len(removed)
                self.collect_macro_definitions()
            else:
                logging.debug("No unused macros found.")
                break
        if total_removed_count > 0:
            logging.info(
                f"Removed a total of {total_removed_count} unused macros."
            )
        else:
            logging.info("No macros pruned.")

    def _normalize_xml_declaration(self, text: str) -> str:
        """Ensure XML declaration uses double quotes."""
        return re.sub(
            r"<\?xml version='1\.0' encoding='utf-8'\?>",
            '<?xml version="1.0" encoding="utf-8"?>',
            text,
        )

    def _escape_em_dashes(self, text: str) -> str:
        """Replace em-dashes with numeric entities."""
        return re.sub(r"—+", lambda m: "&#8212;" * len(m.group(0)), text)

    def normalize_xml_content(self, xml_data: bytes) -> bytes:
        """Revert Python changes to XML content and reorder the default-locale attribute in <style> tags."""
        text = xml_data.decode("utf-8")
        text = self._normalize_xml_declaration(text)
        text = self._escape_em_dashes(text)

        # Collapse XML fragments inside multi-line comments to match CSL repository indentation
        # Pattern captures the entire comment body (non-greedy) so we can post-process line breaks
        comment_pattern = re.compile(r"<!--(.*?)-->", re.DOTALL)

        def collapse_comment(match: re.Match) -> str:
            body = match.group(1)
            # Quick exit if no newline (single-line comment)
            if "\n" not in body:
                return f"<!--{body}-->"
            lines = body.split("\n")
            tag_line_regex = re.compile(r"^[ \t]*<[^>]+>[ \t]*$")
            new_lines: list[str] = []
            i = 0
            while i < len(lines):
                if tag_line_regex.match(lines[i]):
                    # Gather consecutive tag-only lines
                    seq: list[str] = []
                    while i < len(lines) and tag_line_regex.match(lines[i]):
                        seq.append(lines[i])
                        i += 1
                    # Collapse sequence
                    indent_match = re.match(r"^([ \t]*)", seq[0])
                    indent = indent_match.group(1) if indent_match else ""
                    collapsed = indent + "".join(s.strip() for s in seq)
                    new_lines.append(collapsed)
                else:
                    new_lines.append(lines[i])
                    i += 1
            collapsed_body = "\n".join(new_lines)
            return f"<!--{collapsed_body}-->"

        text = comment_pattern.sub(collapse_comment, text)

        # Reorder the default-locale attribute to the end in <style ...> tags.
        def reorder_default_locale(match: re.Match) -> str:
            attribs = match.group(1)
            attrs = re.findall(r'(\S+="[^"]*")', attribs)

            # Separate default-locale from other attributes
            other_attrs = [
                a for a in attrs if not a.startswith("default-locale=")
            ]
            locale_attrs = [a for a in attrs if a.startswith("default-locale=")]

            # Reorder: other attributes first, then locale
            new_attribs = " ".join(other_attrs + locale_attrs)
            return f"<style {new_attribs}>"

        text = re.sub(r"<style\s+([^>]+)>", reorder_default_locale, text)
        return text.encode("utf-8")

    def reindent_xml_bytes(self, xml_data: bytes) -> bytes:
        """Reindent the XML by stripping blank text nodes and pretty-printing.

        This should be applied as a final structural formatter to ensure
        consistent indentation after all tree edits and notice insertion.
        """
        try:
            parser = etree.XMLParser(remove_blank_text=True)
            root = etree.fromstring(xml_data, parser)
            new_tree = etree.ElementTree(root)
            return etree.tostring(
                new_tree,
                encoding="utf-8",
                xml_declaration=True,
                pretty_print=True,
            )
        except Exception:
            # If reindent fails for any reason, fall back to the original bytes
            logging.warning(
                "Reindent step failed; writing original formatted XML.",
                exc_info=True,
            )
            return xml_data

    def save(self) -> None:
        if self.tree is not None:
            try:
                # Insert notice comment if set
                if self.notice_comment and self.root is not None:
                    # Add spaces around comment text for proper XML comment formatting
                    comment_text = f" {self.notice_comment.strip()} "
                    self.root.insert(0, etree.Comment(comment_text))

                # Serialize from the element root to avoid including any
                # document-level processing instructions (e.g., xml-model)
                xml_data = etree.tostring(
                    self.root if self.root is not None else self.tree,
                    encoding="utf-8",
                    xml_declaration=True,
                    pretty_print=True,
                )
                # Normalize textual content, then reindent the entire file
                xml_data = self.normalize_xml_content(xml_data)
                xml_data = self.reindent_xml_bytes(xml_data)
                # Ensure XML declaration uses double quotes
                xml_text = xml_data.decode("utf-8")
                xml_text = self._normalize_xml_declaration(xml_text)
                # lxml will decode character entities during reparse; restore em-dashes as numeric entities
                xml_text = self._escape_em_dashes(xml_text)
                self.output_path.write_text(xml_text, encoding="utf-8")
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
        # Inline trivial macro-only layouts so wrapper macros become removable
        pruner.flatten_layout_macros()
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
