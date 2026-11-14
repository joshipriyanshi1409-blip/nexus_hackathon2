# Linux/macOS convenience targets. On Windows use setup.bat / run.bat instead.
PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: setup run migrate seed test test-live eval

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements-dev.txt

setup: $(BIN)/python
	cp -n .env.example .env || true
	@echo "Edit .env (Supabase keys, ADMIN_PASSWORD), then run: make migrate && $(BIN)/python -m backend.create_ceo"

run: $(BIN)/python
	$(BIN)/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

migrate: $(BIN)/python
	$(BIN)/python -m backend.migrate

seed: $(BIN)/python
	$(BIN)/python -m backend.seed_demo

# Offline tests only (live tests are skipped).
test: $(BIN)/python
	$(BIN)/python -m pytest -q

# Hits the real Supabase project, model and browser. Needs a configured .env.
test-live: $(BIN)/python
	RUN_LIVE_TESTS=1 $(BIN)/python -m pytest -m live -v

# Rules-only benchmark. Add ARGS=--llm to include real model calls.
eval: $(BIN)/python
	$(BIN)/python tests/run_evaluation.py $(ARGS)
