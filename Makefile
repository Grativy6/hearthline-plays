PYTHON ?= python3.12
BUILD_DIR ?= build
USERNAME ?=
ACCELERATOR ?= cpu
GRANT ?=
STAGE_RECEIPT ?=

.PHONY: help package verify-candidate test gate-a gate-b

help:
	@echo "Offline targets only:"
	@echo "  make package [USERNAME=slug] [ACCELERATOR=cpu]"
	@echo "  make verify-candidate"
	@echo "  make test"
	@echo "  make gate-a GRANT=.hearthline/grants/stage.json"
	@echo "  make gate-b GRANT=.hearthline/grants/competition.json STAGE_RECEIPT=.hearthline/receipts/stage.json"
	@echo "No target authenticates, contacts Kaggle, stages a kernel, or submits."

package:
	$(PYTHON) -I -B scripts/build_notebook.py --output-dir "$(BUILD_DIR)" --accelerator "$(ACCELERATOR)" $(if $(USERNAME),--username "$(USERNAME)",)

verify-candidate:
	$(PYTHON) -I -B scripts/verify_candidate.py --build-dir "$(BUILD_DIR)" --require-clean --receipt "$(BUILD_DIR)/verification.json"

test:
	$(PYTHON) -I -B tools/repository_guard.py
	$(PYTHON) -I -B tools/validate_launchpad.py
	$(PYTHON) -I -B -m unittest discover -s tests -p 'test_*.py' -v
	$(PYTHON) -I -B -m unittest discover -s launch/tests -p 'test_*.py' -v

gate-a:
	@test -n "$(GRANT)" || { echo "GRANT is required" >&2; exit 2; }
	$(PYTHON) -I -B scripts/verify_human_gate.py --phase stage --grant "$(GRANT)" --build-dir "$(BUILD_DIR)" --consume

gate-b:
	@test -n "$(GRANT)" || { echo "GRANT is required" >&2; exit 2; }
	@test -n "$(STAGE_RECEIPT)" || { echo "STAGE_RECEIPT is required" >&2; exit 2; }
	$(PYTHON) -I -B scripts/verify_human_gate.py --phase competition --grant "$(GRANT)" --build-dir "$(BUILD_DIR)" --stage-receipt "$(STAGE_RECEIPT)" --consume
