# TokenBench reproducibility entrypoint (Chunk 4 deliverable #5).
#
# Reproduces a single cell from a clean checkout:
#   make repro TASK=needle-click-0000
#
# This is the stranger-test target. It must succeed end-to-end with no
# manual editing for exit gate #1 to pass.

ROOT := $(shell cd .. && pwd)
PYTHON ?= python3
VENV   := $(ROOT)/.venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python

PROVIDER ?= rag-bm25
MODEL    ?= bedrock.anthropic.claude-sonnet-4-5

.PHONY: all repro venv install snapshot verify docker run-cell help

help:
	@echo "TokenBench repro targets:"
	@echo "  make repro TASK=<task_id>          full pipeline: snapshot -> verify -> run cell"
	@echo "  make verify                        verify all snapshots"
	@echo "  make snapshot                      pull pinned repos to artifacts/repos/"
	@echo "  make docker                        build per-repo snapshot containers"
	@echo "  make install                       create .venv, install pinned deps"
	@echo ""
	@echo "Optional vars:  PROVIDER=<name>  MODEL=<name>"

repro: install verify run-cell

install: $(PY)
$(PY):
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(ROOT)/repro/requirements.lock.txt
	$(PIP) install -e $(ROOT)

snapshot: install
	$(PY) $(ROOT)/scripts/snapshot_repos.py

verify: snapshot
	$(PY) $(ROOT)/scripts/verify_snapshot.py

docker: verify
	$(PY) $(ROOT)/scripts/build_images.py

run-cell:
	@if [ -z "$(TASK)" ]; then echo "ERROR: set TASK=<task_id>, e.g. TASK=needle-click-0000"; exit 2; fi
	$(PY) $(ROOT)/repro/run_cell.py --task $(TASK) --provider $(PROVIDER) --model $(MODEL)
