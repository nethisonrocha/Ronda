UV ?= uv

.PHONY: sync test lint format api data

sync:
	$(UV) sync

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

api:
	$(UV) run uvicorn ronda.api.main:app --reload

# make data, ou make data DATASET=ait-ads para baixar só um.
data:
	$(UV) run python scripts/download_data.py $(if $(DATASET),--dataset $(DATASET))

# make up e make demo entram junto com deploy/compose (fase 2) e o modo replay (fase 3).
