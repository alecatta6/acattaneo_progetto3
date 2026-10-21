# GreenThumb Customer Care Agent

ReAct conversational agent for the first-level customer care of **GreenThumb Marketplace**, a
fictional gardening e-commerce (seeds, bulbs, tools, pots, soils, fertilisers). The agent answers
product, agronomic, order and returns questions from a curated knowledge base, and recognises when
a human operator is needed.

Master's project in AI Solution Architecture. The final deliverable is a public Google Colab
notebook that clones this repository; the repository is where the work happens.

**[Open the delivery notebook in Colab](https://colab.research.google.com/github/alecatta6/acattaneo_progetto3/blob/main/notebooks/greenthumb_delivery.ipynb)**
— it carries the technical report and the saved outputs of every cell, so it can be read
without being re-run. Running it needs two Colab Secrets (below).

> **Status: phase 9 (delivery notebook).** Phases 0-8 are complete: data, retrieval, tools,
> agent, memory, response assembly, evaluation and API. See [docs/PLAN.md](docs/PLAN.md) for the
> phase ordering and [eval/results/summary.md](eval/results/summary.md) for the measured results.

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

`.env` is never committed. On Colab the same variables come from Secrets, and two of them
are required rather than optional: `OPENAI_API_KEY` and `GREENTHUMB_LLM_MODEL`. There is no
`.env` to fall back on there, and the model identifier has no safe default — a guessed model
is worse than an error (ADR-076).

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

## Running the API

```bash
make index    # once: builds the vector store (the agent cannot retrieve without it)
make serve    # starts uvicorn on http://localhost:8000
```

`GET /health` reports the business date, the configured models and whether the vector store is
ready — useful to check before the first request, and it reveals no secret.

```bash
curl -s http://localhost:8000/health
```

### A single question

The example from the assignment. The business date is simulated and fixed to 12 October 2026
(ADR-003), so "tomorrow" is 13 October regardless of when you run this.

```bash
curl -s -X POST http://localhost:8000/chat   -H 'Content-Type: application/json'   -d '{"message": "Quando arriva il mio ordine 1042? Posso piantare adesso i bulbi di tulipano?"}'
```

The body carries exactly the four fields the assignment fixes:

```json
{
  "answer": "L'ordine 1042 e' stato spedito con BRT e la consegna stimata e' domani, 13 ottobre. Sui tulipani siamo nella finestra giusta: si mettono a dimora da meta' ottobre a fine novembre, a 12-15 cm di profondita' e 10 cm di distanza.",
  "confidence": "high",
  "sources": ["guides/bulbi_autunnali.md"],
  "needs_human": false
}
```

The session identifier is **not** in the body, so that the contract stays at four fields: it comes
back in the `X-Session-Id` header. Add `-i` to see it.

### A multi-turn conversation

Capture the session from the first reply and pass it back, which is what lets the agent resolve
"quelli dell'ordine di prima".

```bash
SESSION=$(curl -s -i -X POST http://localhost:8000/chat   -H 'Content-Type: application/json'   -d '{"message": "Ho un ordine 1046 in arrivo, cosa contiene?"}'   | awk -F': ' '/^[Xx]-[Ss]ession-[Ii]d/ {print $2}' | tr -d '\r')

curl -s -X POST http://localhost:8000/chat   -H 'Content-Type: application/json'   -d "{\"message\": \"A che profondita' vanno piantati quelli dell'ordine di prima?\", \"session_id\": \"$SESSION\"}"
```

To forget a conversation:

```bash
curl -s -X DELETE "http://localhost:8000/sessions/$SESSION"
```

### Error behaviour

| Situation | Response |
|---|---|
| Empty message, over 2000 characters, unknown field | `422`, before any model call |
| Provider unreachable | `200` with the four-field courtesy reply, `needs_human: true`, and `X-Fallback: true` |

The status stays 200 on a provider failure because the assignment fixes the contract; the header is
what keeps the outage observable (ADR-009).

## License

Coursework project, not for production use.
