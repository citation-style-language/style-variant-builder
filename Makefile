# Generate dependent CSL styles from a template

DIFF_DIR = diffs

CHICAGO_TEMPLATE = chicago-fullnote-bibliography.csl

CHICAGO_DERIVATIVES = chicago-annotated-bibliography \
	chicago-author-date \
	chicago-fullnote-bibliography-short-title-subsequent \
	chicago-fullnote-bibliography-with-ibid \
	chicago-note-bibliography-with-ibid \
	chicago-note-bibliography

# Intermediate files without pruning
CHICAGO_RAW = $(CHICAGO_DERIVATIVES:=.raw.csl)
# Final files after pruning
CHICAGO = $(CHICAGO_DERIVATIVES:=.csl)

all: pruned   ## Build pruned bibliography files (default).

unpruned: $(CHICAGO_RAW)   ## Generate unpruned (diff-applied) bibliography files.

pruned: $(CHICAGO)   ## Generate final bibliography files without unused macros.

# Generate the raw (patched) .csl file.
%.raw.csl: $(CHICAGO_TEMPLATE) $(DIFF_DIR)/%.diff
	@cp $(CHICAGO_TEMPLATE) $@
	@patch $@ $(DIFF_DIR)/$*.diff
	@rm -f $@.orig

# Generate the final pruned .csl file from the raw file.
%.csl: %.raw.csl
	@poetry run python csl_builder/remove_unused_macros.py $< $@   ## Prune unused macros.
	@sed -i '' "s/<?xml version='1.0' encoding='UTF-8'?>/<?xml version=\"1.0\" encoding=\"utf-8\"?>/" $@
	@rm -f $<

help:   ## Display this help message.
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | \
		sort | \
		awk 'BEGIN {FS = ":[^:#]*## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

clean:   ## Remove generated bibliography files.
	@rm -f $(CHICAGO) $(CHICAGO_RAW)

.PHONY: all unpruned pruned help clean
