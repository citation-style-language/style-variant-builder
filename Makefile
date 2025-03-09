# Generate dependent CSL styles from a template

DIFF_DIR = diffs

CHICAGO_TEMPLATE = chicago-fullnote-bibliography.csl

# Automatically generate the list of derivatives from all .diff files in the diffs folder.
DIFF_FILES := $(wildcard $(DIFF_DIR)/*.diff)
CHICAGO_DERIVATIVES := $(basename $(notdir $(DIFF_FILES)))

# Intermediate files without pruning
CHICAGO_RAW = $(CHICAGO_DERIVATIVES:=.raw.csl)
# Final files after pruning
CHICAGO = $(CHICAGO_DERIVATIVES:=.csl)

all: pruned   ## Build pruned bibliography files (default).

unpruned: $(CHICAGO_RAW)   ## Generate unpruned bibliography files for diff creation.

pruned: $(CHICAGO)   ## Generate final bibliography files without unused macros.

# Generate the raw (patched) .csl file.
%.raw.csl: $(CHICAGO_TEMPLATE) $(DIFF_DIR)/%.diff
	@cp $(CHICAGO_TEMPLATE) $@
	@patch $@ $(DIFF_DIR)/$*.diff
	@rm -f $@.orig

# Generate the final pruned .csl file from the raw file.
%.csl: %.raw.csl
	@poetry run python csl_builder/remove_unused_macros.py $< $@
	@rm -f $<

help:   ## Display this help message.
	@echo "Usage: make <target>"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":[^:#]*## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

clean:   ## Remove generated bibliography files.
	@rm -f $(CHICAGO) $(CHICAGO_RAW)

.PHONY: all unpruned pruned help clean
