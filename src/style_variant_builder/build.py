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
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

from style_variant_builder.prune import CSLPruner

logging.basicConfig(level=logging.INFO, format="%(message)s")
TEMPLATE_SUFFIX = "-template.csl"


class ColourFormatter(logging.Formatter):
    """Custom formatter to add colours to log messages."""

    COLOURS = {
        "WARNING": "\033[1;33m",  # Bright Yellow
        "ERROR": "\033[1;31m",  # Bright Red
    }
    RESET = "\033[0m"
    GREEN = "\033[32m"  # Green for success

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, "")
        message = super().format(record)
        return f"{colour}{message}{self.RESET}"


# Apply the custom formatter to the root logger
handler = logging.StreamHandler()
handler.setFormatter(ColourFormatter("%(message)s"))
logging.getLogger().handlers = [handler]


class ErrorCountingFilter(logging.Filter):
    """Filter that counts ERROR and higher log records while passing all records through."""

    def __init__(self) -> None:
        super().__init__()
        self.error_count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            self.error_count += 1
        return True


# Global instance to track error count across the entire run
_error_count_filter = ErrorCountingFilter()
logging.getLogger().addFilter(_error_count_filter)


@dataclass(slots=True)
class CSLBuilder:
    """Builder for CSL style variants with parallel processing support."""

    templates_dir: Path
    diffs_dir: Path
    output_dir: Path
    development_dir: Path
    style_family: str
    export_development: bool = False
    generate_diffs: bool = False
    group_by_family: bool = True
    max_workers: int | None = None
    successful_variants: int = 0
    failed_variants: int = 0

    @staticmethod
    def _generate_single_diff(
        dev_file: Path,
        template_lines: list[str],
        template_path: Path,
        diffs_dir: Path,
    ) -> tuple[str, bool, str]:
        """
        Generate a diff file for a single development file.

        Returns: (filename, success, message)
        """
        try:
            with dev_file.open("r", encoding="utf-8") as df:
                dev_lines = df.readlines()

            diff = list(
                difflib.unified_diff(
                    template_lines,
                    dev_lines,
                    fromfile=str(template_path),
                    tofile=str(dev_file),
                    lineterm="\n",
                )
            )

            if not diff:
                return (
                    dev_file.name,
                    True,
                    f"  ≈ {dev_file.stem}",
                )

            diff_path = diffs_dir / dev_file.with_suffix(".diff").name
            diffs_dir.mkdir(parents=True, exist_ok=True)
            diff_path.write_text("".join(diff), encoding="utf-8")
            return (dev_file.name, True, f"  ✓ {diff_path.name}")

        except Exception as e:
            return (dev_file.name, False, f"Error generating diff: {e}")

    @staticmethod
    def _process_single_diff(
        diff_path: Path,
        template_path: Path,
        target_output_dir: Path,
        development_dir: Path | None,
        export_development: bool,
    ) -> tuple[str, bool, str]:
        """
        Process a single diff file in a worker process.

        Returns: (diff_name, success, message)
        """
        patched_file = None
        try:
            # Apply the patch
            if not shutil.which("patch"):
                return (
                    diff_path.name,
                    False,
                    "Required command 'patch' not found in PATH.",
                )

            with tempfile.NamedTemporaryFile(
                delete=False, mode="w+", encoding="utf-8"
            ) as tmp_file:
                shutil.copy(template_path, tmp_file.name)
                tmp_file_path = Path(tmp_file.name)

            patched_file = tmp_file_path
            result = subprocess.run(
                ["patch", "-s", "-N", str(patched_file), str(diff_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode != 0:
                return (
                    diff_path.name,
                    False,
                    f"Failed to apply patch: {result.stdout}",
                )

            # Export or prune
            if export_development and development_dir is not None:
                dev_variant = (
                    development_dir / diff_path.with_suffix(".csl").name
                )
                shutil.copy(patched_file, dev_variant)
                return (
                    diff_path.name,
                    True,
                    f"  ✓ {dev_variant.stem}",
                )
            else:
                output_variant = (
                    target_output_dir / diff_path.with_suffix(".csl").name
                )
                # Prune the variant
                pruner = CSLPruner(
                    input_path=patched_file,
                    output_path=output_variant,
                )
                pruner.parse_xml()
                pruner.flatten_layout_macros()
                pruner.prune_macros()
                pruner.save()
                return (
                    diff_path.name,
                    True,
                    f"  ✓ {output_variant.stem}",
                )

        except Exception as e:
            return (diff_path.name, False, f"Error processing diff: {e}")

        finally:
            if patched_file is not None:
                with suppress(FileNotFoundError):
                    patched_file.unlink()

    def _get_template_path(self) -> Path:
        template = self.templates_dir / f"{self.style_family}-template.csl"
        if not template.exists():
            raise FileNotFoundError(f"Template not found: {template}")
        return template

    def _get_diff_files(self) -> list[Path]:
        # Collect diff files that match the expected naming convention.
        filename_diffs = set(self.diffs_dir.glob(f"{self.style_family}*.diff"))
        reference_diffs = []
        # Also examine all diff files for an internal reference to the template.
        for diff_file in self.diffs_dir.glob("*.diff"):
            if diff_file in filename_diffs:
                continue
            try:
                with diff_file.open("r", encoding="utf-8") as f:
                    content = f.read()
                # Check for a template reference line, for example rel="template" that contains the expected style family.
                if (
                    'rel="template"' in content
                    and f"/{self.style_family}" in content
                ):
                    reference_diffs.append(diff_file)
            except Exception as e:
                logging.error(
                    f"Error reading diff file {diff_file.name}: {e}",
                    exc_info=True,
                )
        all_diffs = sorted(chain(filename_diffs, reference_diffs))
        if not all_diffs:
            raise FileNotFoundError(
                f"No diff files found for style family '{self.style_family}' in {self.diffs_dir}"
            )
        return all_diffs

    def build_variants(self) -> tuple[int, int]:
        try:
            template_path = self._get_template_path()
        except FileNotFoundError as e:
            logging.warning(f"Skipping style family '{self.style_family}': {e}")
            return (0, 0)
        try:
            diff_files = self._get_diff_files()
        except FileNotFoundError as e:
            logging.warning(f"Skipping style family '{self.style_family}': {e}")
            return (0, 0)

        # Prepare output directory (optionally group by family)
        target_output_dir = (
            self.output_dir / self.style_family
            if self.group_by_family
            else self.output_dir
        )
        target_output_dir.mkdir(parents=True, exist_ok=True)
        if self.export_development:
            self.development_dir.mkdir(parents=True, exist_ok=True)

        # Process diff files in parallel
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(
                    CSLBuilder._process_single_diff,
                    diff_path,
                    template_path,
                    target_output_dir,
                    self.development_dir if self.export_development else None,
                    self.export_development,
                )
                for diff_path in diff_files
            ]

            for future in as_completed(futures):
                diff_name, success, message = future.result()
                if success:
                    logging.info(message)
                    self.successful_variants += 1
                else:
                    logging.error(f"  ✗ {diff_name}: {message}")
                    self.failed_variants += 1

        return (self.successful_variants, self.failed_variants)

    def generate_diff_files(self) -> None:
        try:
            template_path = self._get_template_path()
        except FileNotFoundError as e:
            logging.warning(
                f"Skipping diff generation for style family '{self.style_family}': {e}"
            )
            return

        # Collect development files that match the expected naming convention.
        expected_dev_files = set(
            self.development_dir.glob(f"{self.style_family}*.csl")
        )
        additional_dev_files = []
        # Examine .csl files for internal references to the template.
        for dev_file in self.development_dir.glob("*.csl"):
            if dev_file in expected_dev_files:
                continue
            try:
                with dev_file.open("r", encoding="utf-8") as f:
                    content = f.read()
                if (
                    'rel="template"' in content
                    and f"/{self.style_family}" in content
                ):
                    additional_dev_files.append(dev_file)
            except Exception as e:
                logging.error(
                    f"Error reading development file {dev_file.name}: {e}",
                    exc_info=True,
                )
        dev_files = sorted(chain(expected_dev_files, additional_dev_files))

        if not dev_files:
            logging.warning(
                f"Skipping diff generation: No development CSL files found for style family '{self.style_family}' in {self.development_dir}"
            )
            return

        with template_path.open("r", encoding="utf-8") as tf:
            template_lines = tf.readlines()

        # Process diff generation in parallel
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(
                    CSLBuilder._generate_single_diff,
                    dev_file,
                    template_lines,
                    template_path,
                    self.diffs_dir,
                )
                for dev_file in dev_files
            ]

            for future in as_completed(futures):
                filename, success, message = future.result()
                if success:
                    logging.info(message)
                else:
                    logging.error(f"  ✗ {filename}: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
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
    parser.add_argument(
        "--flat-output",
        action="store_true",
        help="Write pruned output styles into a flat output directory (no per-family subfolders).",
    )
    parser.add_argument(
        "--max-workers",
        "-w",
        type=int,
        default=None,
        help="Maximum number of parallel workers. Default is the number of CPU cores.",
    )

    args = parser.parse_args()

    # Automatically determine style families by scanning template files.
    template_files = list(args.templates_path.glob(f"*{TEMPLATE_SUFFIX}"))
    if not template_files:
        logging.error(f"No template files found in {args.templates_path}.")
        return 1
    style_families = [
        template.stem.removesuffix(TEMPLATE_SUFFIX.removesuffix(".csl"))
        for template in template_files
    ]

    # Print mode indicator
    if args.diffs:
        logging.info("Mode: \033[1;35mGenerating diff files\033[0m\n")
    elif args.development:
        logging.info(
            "Mode: \033[1;35mBuilding development variants (unpruned)\033[0m\n"
        )
    else:
        logging.info("Mode: \033[1;35mBuilding production variants\033[0m\n")

    overall_success = True
    family_results = {}  # Track results per family

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
            group_by_family=(not args.flat_output),
            max_workers=args.max_workers,
        )
        try:
            if args.diffs:
                builder.generate_diff_files()
                family_results[style_family] = (
                    0,
                    0,
                )  # diff generation doesn't track variants
            else:
                successful, failed = builder.build_variants()
                family_results[style_family] = (successful, failed)
                # Consider it a failure if any variants failed to build
                if failed > 0:
                    overall_success = False
        except Exception as e:
            overall_success = False
            family_results[style_family] = (0, 1)  # Mark as failed
            logging.error(
                f"Error processing style family {style_family}: {e}",
                exc_info=True,
            )
    # Summary reporting
    if not args.diffs:  # Only report variant stats for build mode
        total_successful = sum(
            successful for successful, failed in family_results.values()
        )
        total_failed = sum(
            failed for successful, failed in family_results.values()
        )
        failed_families = [
            family
            for family, (successful, failed) in family_results.items()
            if successful == 0 and failed > 0
        ]

        if failed_families:
            logging.error(
                f"Style families with no successful builds: {', '.join(failed_families)}"
            )

        if total_successful > 0:
            logging.info(
                f"Successfully built {total_successful} variants across {len(style_families)} style families."
            )

        if total_failed > 0:
            logging.error(f"Failed to build {total_failed} variants.")

    # Summary if any errors occurred
    if _error_count_filter.error_count:
        error_word: str = (
            "error" if _error_count_filter.error_count == 1 else "errors"
        )
        logging.error(
            f"Run completed with {_error_count_filter.error_count} {error_word}."
        )
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
