# CSL Builder

`csl-builder` is a tool designed to help maintain a family of Citation Style Language (CSL) styles. It allows you to define a single template for a style family and generate multiple variants by applying modifications (diffs). The tool also prunes unused macros from the final styles to ensure they are clean and efficient.

## System Requirements

Before using `csl-builder`, ensure your system has available:

- [**`uv`**](https://docs.astral.sh/uv/): A package manager for Python that executes commands in a virtual environment.
- **`make`**: A build automation tool that is typically pre-installed on Unix-like systems. It runs the provided `Makefile`.
- **`patch`**: A command-line tool for applying diff files. Ensure it is installed and available in your system's PATH.

## Installation

Clone the repository and ensure the required tools are installed. You can then use the provided `Makefile` to run tasks.

## Usage

### Creating a new style family

Follow these steps to create and maintain a new family of CSL styles:

1. **Create a template in `templates`**
   - Add a new template file in the `templates` directory.
   - Name the file in the format `<style-name>-template.csl`. The `<style-name>` can be used to match the template with the variant files, if the template and variant files begin with the same prefix. If the script cannot match a variant with its template by file name, it will check for a linked `template` within the file itself.
   - The template should include all macros to which any variant in the family refers (such as macros for both notes and author–date styles). The build script will automatically prune unused macros in the final files.

2. **Run `make dev` to create development styles**
   - Use the command:
     ```bash
     make dev
     ```
   - This will generate variant styles from available diffs in the `development` directory. These styles retain all macros to avoid unnecessary changes when compared to the template. By minimizing the number of changes in comparison to the template, the diff files will be smaller and easier to maintain when changes to the template are made.
   - If a change of more than one or two lines is needed, consider adding a new macro to the template and referring to it rather than modifying the development style directly.

3. **Duplicate the template in the `development` folder**
   - Copy the template file from `templates` to the `development` directory.
   - Rename the copied file to match the variant you want to create (e.g. `<style-name>-variant.csl`).

4. **Modify the development CSL style**
   - Edit the copied file in the `development` directory to make the necessary changes for the specific variant.

5. **Run `make diffs` to create diff files**
   - Use the command:
     ```bash
     make diffs
     ```
   - This will generate `.diff` files for all variants in the `development` folder. These files record the differences between the template and the modified development files. The diff files are used to create the final styles.

6. **Run `make` to build final styles**
   - Use the command:
     ```bash
     make
     ```
   - This will generate the final pruned styles in the `output` directory. Unused macros will be removed from these styles.

### Cleaning up

To remove all generated files (in `output` and `development`), run:
```bash
make clean
```

## Directory structure

- `templates`: Contains the base templates for each style family.
- `development`: Contains unpruned development styles for modification.
- `diffs`: Contains `.diff` files that record changes between templates and development styles.
- `output`: Contains the final pruned styles.

## Example workflow

Suppose you want to create a new style family called `example-style`:

1. Add `example-style-template.csl` to the `templates` directory.
2. Run `make dev` to generate unpruned styles in `development/`.
3. Copy `example-style-template.csl` to `development/example-style-note.csl` and modify it for the "note" variant.
4. Run `make diffs` to generate `diffs/example-style-note.diff`.
5. Run `make` to generate the final pruned style in `output/example-style-note.csl`.

## Notes

- Ensure that the `patch` command is installed and available in your PATH.