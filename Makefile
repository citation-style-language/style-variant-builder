# Phony targets ensure commands always run
.PHONY: final unpruned diffs clean help

final: ## Build CSL variants with default style families
	@uv run python3 -m csl_builder.build

dev: ## Build unpruned CSL variants for development
	@uv run python3 -m csl_builder.build --development

diffs: ## Regenerate diff patches from development
	@uv run python3 -m csl_builder.build --diffs

clean: ## Remove output directories
	@rm -rf output development

# Help target: Lists targets and their inline comments in a neatly aligned, coloured format.
help:
	@echo "Usage: make [target]\n"
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sort | awk -F '##' '{printf "\033[1;32m%-15s\033[0m - %s\n", $$1, $$2}'
