UV ?= uv
COMPOSE ?= docker compose -f deploy/compose/dev.yml --env-file .env

.PHONY: sync test lint format api data up down ps logs reset

sync:
	$(UV) sync --all-extras

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

# Ambiente local: PostgreSQL e Redis (deploy/compose/dev.yml). Requer o .env (veja .env.example).
up:
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

# Apaga os volumes: banco e Redis voltam vazios no próximo `make up`.
reset:
	$(COMPOSE) down -v
