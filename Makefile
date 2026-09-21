# GreenThumb — developer entry points. Everything runs through `uv run`.
.PHONY: help setup data index test test-llm lint format eval serve

help:
	@echo "setup     uv sync + install pre-commit hooks"
	@echo "data      generate orders.json and validate the knowledge base"
	@echo "index     (re)build the Chroma vector store"
	@echo "test      pytest unit tests (no LLM calls)"
	@echo "test-llm  integration tests against a real LLM (requires .env)"
	@echo "lint      ruff check + ruff format --check"
	@echo "format    ruff format + ruff check --fix"
	@echo "eval      run the full evaluation (costly: asks for confirmation)"
	@echo "serve     start the FastAPI app on http://localhost:8000"

setup:
	uv python install 3.12
	uv sync
	uv run pre-commit install

data:
	uv run python scripts/generate_orders.py
	uv run python scripts/validate_data.py

index:
	uv run python scripts/build_index.py

test:
	uv run pytest -m "not llm"

test-llm:
	uv run pytest -m llm

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

eval:
	@echo "The full evaluation performs many LLM calls (agent + judge) and costs money."
	@printf "Continue? [y/N] " && read ans && [ "$$ans" = "y" ]
	uv run python -m eval.runner
	uv run python -m eval.metrics_ragas
	uv run python -m eval.metrics_deepeval
	uv run python -m eval.metrics_deterministic

serve:
	uv run uvicorn greenthumb.api:app --host 0.0.0.0 --port 8000
