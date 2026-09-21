# GreenThumb Customer Care Agent

ReAct conversational agent for the first-level customer care of **GreenThumb Marketplace**, a
fictional gardening e-commerce (seeds, bulbs, tools, pots, soils, fertilisers). The agent answers
product, agronomic, order and returns questions from a curated knowledge base, and recognises when
a human operator is needed.

Master's project in AI Solution Architecture. The final deliverable is a public Google Colab
notebook that clones this repository; the repository is where the work happens.

> **Status: phase 0 (bootstrap).** Most `make` targets below refer to code that does not exist
> yet. See [docs/PLAN.md](docs/PLAN.md) for the phase ordering.

## Documentation

| Document | Contents |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Technical specification and requirement traceability |
| [docs/PLAN.md](docs/PLAN.md) | Phased work plan with a Definition of Done per phase |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture decision records — the source material for the report |

## Requirements

- Python 3.12 (installed by `make setup` through `uv`)
- [uv](https://docs.astral.sh/uv/)
- An OpenAI API key

## Setup

```bash
make setup
cp .env.example .env   # then fill in OPENAI_API_KEY
```

`.env` is never committed. On Colab the same variables come from Secrets.

## Commands

| Command | Purpose |
|---|---|
| `make setup` | Install Python 3.12, sync dependencies, install pre-commit hooks |
| `make data` | Generate `orders.json` and validate the knowledge base |
| `make index` | (Re)build the Chroma vector store |
| `make test` | Unit tests, no LLM calls |
| `make test-llm` | Integration tests against a real LLM |
| `make lint` | `ruff check` + `ruff format --check` |
| `make eval` | Full evaluation (costly — asks for confirmation) |
| `make serve` | Start the FastAPI app on <http://localhost:8000> |

## License

Coursework project, not for production use.
