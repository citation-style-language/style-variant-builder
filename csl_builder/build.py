"""
Construct and manage Citation Style Language (CSL) variants.
"""

import argparse
import difflib
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from csl_builder.prune import CSLPruner

logging.basicConfig(level=logging.INFO, format="%(message)s")


class ColourFormatter(logging.Formatter):
    """Custom formatter to add colours to log messages."""

    COLOURS = {
        "WARNING": "\033[1;33m",  # Bright Yellow
        "ERROR": "\033[1;31m",  # Bright Red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, "")
        message = super().format(record)
        return f"{colour}{message}{self.RESET}"


# Apply the custom formatter to the root logger
handler = logging.StreamHandler()
handler.setFormatter(ColourFormatter("%(message)s"))
logging.getLogger().handlers = [handler]


@dataclass(slots=True)
class CSLBuilder:
    templates_dir: Path
    diffs_dir: Path
    output_dir: Path
    development_dir: Path
    style_family: str
    export_development: bool = False
    generate_diffs: bool = False

    def _get_template_path(self) -> Path:
        template = self.templates_dir / f"{self.style_family}-template.csl"
        if not template.exists():
            raise FileNotFoundError(f"Template not found: {template}")
        return template

    def _get_diff_files(self) -> list[Path]:
        diffs = sorted(self.diffs_dir.glob(f"{self.style_family}*.diff"))
        if not diffs:
            raise FileNotFoundError(
                f"No diff files found for style family '{self.style_family}' in {self.diffs_dir}"
            )
        return diffs

    def _apply_patch(self, template_path: Path, diff_path: Path) -> Path | None:
        # Ensure the 'patch' command is available
        if not shutil.which("patch"):
            raise EnvironmentError(
                "Required command 'patch' not found in PATH."
            )
        with tempfile.NamedTemporaryFile(
            delete=False, mode="w+", encoding="utf-8"
        ) as tmp_file:
            shutil.copy(template_path, tmp_file.name)
            tmp_file_path = Path(tmp_file.name)
        result = subprocess.run(
            ["patch", "-s", "-N", str(tmp_file_path), str(diff_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            logging.error(
                f"Failed to apply patch {diff_path}:\n {result.stdout}"
            )
            tmp_file_path.unlink(missing_ok=True)
            return None  # Fail gracefully by returning None
        return tmp_file_path

    def _prune_variant(self, patched_file: Path, output_variant: Path) -> None:
        pruner = CSLPruner(patched_file, output_variant)
        pruner.parse_xml()
        pruner.prune_macros()
        pruner.save()

    def build_variants(self) -> None:
        try:
            template_path = self._get_template_path()
        except FileNotFoundError as e:
            logging.warning(f"Skipping style family '{self.style_family}': {e}")
            return
        try:
            diff_files = self._get_diff_files()
        except FileNotFoundError as e:
            logging.warning(f"Skipping style family '{self.style_family}': {e}")
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.export_development:
            self.development_dir.mkdir(parents=True, exist_ok=True)
        for diff_path in diff_files:
            patched_file = None
            try:
                logging.info(f"Processing diff: {diff_path.name}")
                patched_file = self._apply_patch(template_path, diff_path)
                if patched_file is None:
                    logging.warning(
                        f"Skipping diff {diff_path.name} due to patch failure."
                    )
                    continue
                if self.export_development:
                    dev_variant = (
                        self.development_dir
                        / diff_path.with_suffix(".csl").name
                    )
                    shutil.copy(patched_file, dev_variant)
                    logging.info(
                        f"Exported development variant to {dev_variant}"
                    )
                else:
                    output_variant = (
                        self.output_dir / diff_path.with_suffix(".csl").name
                    )
                    self._prune_variant(patched_file, output_variant)
                    logging.info(f"Generated variant: {output_variant}")
            except Exception as e:
                logging.error(
                    f"Error processing diff {diff_path.name}: {e}",
                    exc_info=True,
                )
            finally:
                if patched_file is not None and patched_file.exists():
                    patched_file.unlink(missing_ok=True)

    def generate_diff_files(self) -> None:
        try:
            template_path = self._get_template_path()
        except FileNotFoundError as e:
            logging.warning(
                f"Skipping diff generation for style family '{self.style_family}': {e}"
            )
            return
        dev_files = list(self.development_dir.glob(f"{self.style_family}*.csl"))
        if not dev_files:
            logging.warning(
                f"Skipping diff generation: No development CSL files found for style family '{self.style_family}' in {self.development_dir}"
            )
            return
        with template_path.open("r", encoding="utf-8") as tf:
            template_lines = tf.readlines()
        for dev_file in dev_files:
            try:
                with dev_file.open("r", encoding="utf-8") as df:
                    dev_lines = df.readlines()
                diff = list(
                    difflib.unified_diff(
                        template_lines,
                        dev_lines,
                        fromfile=str(template_path),
                        tofile=str(dev_file),
                        lineterm="\n",  # Changed from "" to "\n" for proper header newlines.
                    )
                )
                if not diff:
                    logging.info(f"No differences found for {dev_file.name}.")
                    continue
                diff_path = self.diffs_dir / dev_file.with_suffix(".diff").name
                self.diffs_dir.mkdir(parents=True, exist_ok=True)
                with diff_path.open("w", encoding="utf-8") as dfile:
                    dfile.write("".join(diff))
                logging.info(f"Generated diff file: {diff_path}")
            except Exception as e:
                logging.error(
                    f"Error generating diff for {dev_file.name}: {e}",
                    exc_info=True,
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Removed --style-families argument; style families are now determined automatically.
    # Group all directory options together.
    directories_group = parser.add_argument_group("Directory Options")
    directories_group.add_argument(
        "--templates-path",
        "-T",
        type=Path,
        default=Path("templates"),
        help="Directory containing CSL templates.",
    )
    directories_group.add_argument(
        "--diffs-path",
        "-D",
        type=Path,
        default=Path("diffs"),
        help="Directory containing diff files.",
    )
    directories_group.add_argument(
        "--output-path",
        "-O",
        type=Path,
        default=Path("output"),
        help="Directory to write pruned variants.",
    )
    directories_group.add_argument(
        "--development-path",
        "-E",
        type=Path,
        default=Path("development"),
        help="Directory for development variants or development files.",
    )
    parser.add_argument(
        "--development",
        "-e",
        action="store_true",
        help="Export development variants to the development directory.",
    )
    parser.add_argument(
        "--diffs",
        "-d",
        action="store_true",
        help="Generate new diff files by comparing development files against templates.",
    )

    args = parser.parse_args()

    # Automatically determine style families by scanning template files.
    template_files = list(args.templates_path.glob("*-template.csl"))
    if not template_files:
        logging.error(f"No template files found in {args.templates_path}.")
        return 1
    style_families = [
        template.stem.replace("-template", "") for template in template_files
    ]

    overall_success = True
    for style_family in style_families:
        logging.info(
            f"Processing style family: \033[1;36m{style_family}\033[0m"
        )  # Cyan for style family
        builder = CSLBuilder(
            templates_dir=args.templates_path,
            diffs_dir=args.diffs_path,
            output_dir=args.output_path,
            development_dir=args.development_path,
            style_family=style_family,
            export_development=args.development,
            generate_diffs=args.diffs,
        )
        try:
            if args.diffs:
                builder.generate_diff_files()
            else:
                builder.build_variants()
        except Exception as e:
            overall_success = False
            logging.error(
                f"Error processing style family {style_family}: {e}",
                exc_info=True,
            )
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
