# GreenThumb Customer Care Agent — contesto operativo

Agente conversazionale ReAct per il customer care di un e-commerce fittizio di giardinaggio.
Progetto d'esame del Master in AI Solution Architecture. Il deliverable è un **notebook Colab
pubblico** che clona questo repo; il repo è dove si sviluppa.

## Comandi

Tutto passa da `uv run`. **Mai `pip install`** nel progetto.

```bash
make setup      # uv sync + pre-commit hooks
make data       # genera orders.json e valida la knowledge base
make index      # (ri)costruisce il vector store Chroma
make test       # 317 test unitari, nessuna chiamata LLM
make test-llm   # 23 test di integrazione con provider reale (richiede .env)
make lint       # ruff check + ruff format --check
make format     # ruff format
make eval       # evaluation completa (~300 chiamate, chiede conferma)
make serve      # API FastAPI su http://localhost:8000
```

## Struttura

```
src/greenthumb/  config.py clock.py schemas.py kb_loader.py retrieval.py prompts.py
                 orders_repository.py escalations_repository.py memory.py agent.py
                 response.py (assemblaggio deterministico) service.py (chat()) api.py
                 tools/ {knowledge_base,order_status,escalation}_tool.py
scripts/         generate_orders validate_data build_index probe_retrieval
                 ablation_e5_prefixes demo_tools demo_memory build_notebook
eval/            conversations.jsonl runner.py metrics_{deterministic,ragas,deepeval}.py
                 report.py results/{traces.jsonl,summary.md,before/}
data/            catalog.yaml  kb/{products,guides,policies}/*.md  orders.json
tests/           una suite per modulo; *_integration.py sono marcati `llm`
docs/            CONVENTIONS PLAN SPEC DECISIONS RETRIEVAL_CALIBRATION contesto-sessione
notebooks/       greenthumb_delivery.ipynb (generato, non scritto a mano)
```

## Come leggere questo repo senza bruciare contesto

- `docs/DECISIONS.md` è 118 KB (76 ADR): si legge con `grep -A30 "ADR-0NN" docs/DECISIONS.md`,
  **mai intero**. Ogni numero di ADR citato nel codice o nei doc rimanda là.
- `eval/results/traces.jsonl` è 130 KB (50 turni): si interroga con `python`/`jq`, mai intero.
- `notebooks/greenthumb_delivery.ipynb` è 96 KB con output salvati: si ispeziona estraendo le
  celle con `json`, non con una lettura diretta.
- Ordine di lettura utile: `docs/contesto-sessione.md` (stato, decisioni portanti, cosa è
  aperto) → `docs/CONVENTIONS.md` (convenzioni e insidie delle librerie) → `docs/PLAN.md`.

## Convenzioni

- Nomi, docstring, commenti e commit in **inglese**; tutto ciò che legge il cliente
  (knowledge base, prompt, risposte) in **italiano**.
- `snake_case` funzioni/variabili/moduli, `CamelCase` classi, `UPPER_SNAKE_CASE` costanti.
- **Docstring su ogni** funzione, metodo, classe e test helper, stile Google (Args/Returns/
  Raises). Type hints ovunque; modelli dati Pydantic v2. Verificato da ruff (`D`, `N`, `ANN`).
- Funzioni piccole e testabili: I/O ai bordi, logica pura al centro.
- Nessun segreto nel codice: configurazione **solo** da `src/greenthumb/config.py`.
- Commit piccoli, Conventional Commits, messaggi in inglese.

## Principio architetturale

**Deterministico prima del probabilistico.** Dei quattro campi della risposta solo `answer`
viene dall'LLM: `sources` è l'intersezione fra ciò che il modello cita e ciò che il retrieval
ha restituito sopra soglia, `needs_human` deriva dal registro delle escalation della sessione,
`confidence` è il minimo fra la proposta del modello e un cap sugli score. Dettagli in
`docs/SPEC.md` §5 e ADR-002.

## Regole di lavoro

1. **Una fase alla volta** secondo `docs/PLAN.md`, che per ogni fase ha una Definition of Done.
   Le fasi marcate `🔍 REVIEW` richiedono che l'utente riveda l'output prima di proseguire.
2. **Ogni scelta non ovvia va in `docs/DECISIONS.md`** in formato ADR (contesto, decisione,
   alternative scartate, conseguenze). È la materia prima della relazione: la valutazione
   premia le motivazioni più del funzionamento.
3. **Non fidarsi della memoria sulle API.** LangChain 1.x, RAGAS 0.4 e DeepEval 4.x hanno API
   diverse da quasi tutto il materiale online. Verificare sul pacchetto installato
   (`python -c "import inspect, X; print(inspect.signature(...))"`) o sulla documentazione.
4. **Se una specifica è ambigua o sembra sbagliata, chiedere** invece di interpretare in
   silenzio. Se esiste un modo migliore di quello specificato, proporlo prima di implementarlo.
5. Mai committare `.env`, `vector_store/`, `escalations.jsonl`, cache.

## Da non toccare senza averne misurato l'effetto

- **Soglie di retrieval 0.813 / 0.863**: calibrate, separazione di soli +0.0132. Una soglia a 0
  disattiva il filtro **in silenzio** (ADR-043, `docs/RETRIEVAL_CALIBRATION.md`).
- **`summary_trigger_tokens` 6000**: sotto il pavimento misurato di ~2583 la summarization
  scatta a ogni chiamata, e i test diventerebbero *più* verdi, non meno (ADR-056, ADR-072).
- **Il `config: RunnableConfig` del tool di escalation non ha default, di proposito**:
  aggiungerlo disattiva l'iniezione senza errori e unisce tutte le sessioni (ADR-047).
- **`langchain-community==0.3.31`**: pin fragile ma necessario, senza cui `import ragas` muore
  (ADR-019).
- **`expected_sources` del dataset di evaluation**: non allargarli per far salire le metriche
  (ADR-045).
- **Notebook e `eval/results/summary.md` sono generati**: modificarli a mano funziona una volta,
  poi la rigenerazione cancella tutto. Si modificano i generatori.
- **Il `.env` locale vince sui default calibrati**: un valore copiato e dimenticato è già
  costato tre volte (ADR-043, ADR-072).

## Stato

Fasi 0-8 chiuse. **Fase 9 aperta**: il notebook non è ancora stato eseguito su un runtime Colab
pulito, gli output committati sono locali. Servono due Secrets, non uno: `OPENAI_API_KEY` **e**
`GREENTHUMB_LLM_MODEL` (ADR-076). Difetti noti, misurati e deliberatamente non corretti: vedi
`docs/contesto-sessione.md`, sezione «Aperto, a metà, o noto e non risolto».
