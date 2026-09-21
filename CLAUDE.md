# GreenThumb Customer Care Agent

Progetto d'esame del Master in AI Solution Architecture. Agente conversazionale ReAct per il
customer care di **GreenThumb Marketplace**, e-commerce fittizio di articoli per il giardinaggio
(sementi, bulbi, attrezzi, vasi, terricci, fertilizzanti). L'agente gestisce le richieste di
primo livello e riconosce quando serve un operatore umano.

Il deliverable finale è un **notebook Google Colab pubblico** che clona questo repository, lo
esegue e contiene la relazione tecnica. Il repository è il luogo dove si sviluppa; il notebook
è l'involucro di consegna.

@docs/SPEC.md
@docs/PLAN.md
@docs/DECISIONS.md

## Regole di lavoro (obbligatorie)

1. **Una fase alla volta.** Segui `docs/PLAN.md` nell'ordine. Non iniziare la fase successiva
   senza approvazione esplicita dell'utente. A fine fase: esegui i controlli della Definition of
   Done, riassumi cosa è stato fatto e cosa resta aperto, poi fermati.
2. **Checkpoint di revisione.** Le fasi marcate `🔍 REVIEW` in PLAN.md richiedono che l'utente
   rivaluti l'output (es. contenuti della knowledge base) prima di proseguire.
3. **Non fidarti della memoria sulle API.** LangChain 1.x, RAGAS 0.4 e DeepEval 4.x hanno API
   cambiate rispetto a gran parte del materiale online e dei dati di addestramento. Prima di
   usare un'API di queste librerie, verificala sulla documentazione ufficiale o ispezionando il
   pacchetto installato (`python -c "import inspect, X; print(inspect.signature(...))"`).
   Registra in `docs/DECISIONS.md` ogni scoperta rilevante.
4. **Ogni scelta architetturale va motivata** in `docs/DECISIONS.md` (formato ADR sintetico:
   contesto, decisione, alternative scartate, conseguenze). È la materia prima della relazione:
   la valutazione premia le motivazioni più del funzionamento.
5. **Commit piccoli e frequenti**, Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`,
   `chore:`, `refactor:`), messaggi in inglese. Mai committare `.env`, vector store o cache.
6. **Se una specifica è ambigua o sembra sbagliata, chiedi** invece di interpretare in silenzio.
   Se trovi un modo migliore di quello specificato, proponilo prima di implementarlo.

## Principio architetturale guida

**Deterministico prima del probabilistico.** L'LLM decide *cosa dire* e *quale tool usare*;
tutto ciò che può essere calcolato dal codice viene calcolato dal codice. In particolare:

- `sources` è derivato dai documenti effettivamente restituiti dal retrieval, mai inventato.
- `needs_human` è `true` se e solo se il tool di escalation è stato invocato con successo nel turno.
- `confidence` proposto dall'LLM viene limitato (cap) da regole deterministiche sulla qualità
  del retrieval.
- La data corrente arriva da un `Clock` iniettato, mai da `datetime.now()` sparso nel codice.

Dettagli in `docs/SPEC.md` §5.

## Comandi

```bash
make setup      # uv sync + installa pre-commit hooks
make data       # genera orders.json e valida la knowledge base
make index      # (ri)costruisce il vector store Chroma
make test       # pytest unit (nessuna chiamata LLM)
make test-llm   # test di integrazione con LLM reale (richiede .env)
make lint       # ruff check + ruff format --check
make eval       # esegue l'evaluation completa (costosa: chiede conferma)
make serve      # avvia l'API FastAPI su http://localhost:8000
```

Tutto passa da `uv run`. Non usare `pip install` direttamente nel progetto.

## Convenzioni di codice (requisiti d'esame, non negoziabili)

- Naming in **inglese**: `snake_case` per funzioni, variabili, moduli; `CamelCase` per le classi;
  `UPPER_SNAKE_CASE` per le costanti.
- **Docstring su ogni funzione, metodo e classe**, stile Google (Args / Returns / Raises).
  Anche per funzioni private e test helper.
- Type hints ovunque; modelli dati con Pydantic v2.
- Contenuti rivolti all'utente finale (knowledge base, prompt, risposte) in **italiano**.
  Codice, commenti, docstring, commit in **inglese**.
- Nessun segreto nel codice: configurazione solo via `src/greenthumb/config.py` (legge `.env`
  in locale, Colab Secrets su Colab).
- Funzioni piccole e testabili; I/O ai bordi, logica pura al centro.

## Insidie note

- **LangChain 1.x**: usare `langchain.agents.create_agent`. Non usare `AgentExecutor`,
  `initialize_agent` o il vecchio `create_react_agent` con prompt da LangChain Hub: sono API legacy.
- **Embedding e5**: `multilingual-e5-base` richiede i prefissi `"query: "` per le query e
  `"passage: "` per i documenti. Senza, la qualità del retrieval crolla in modo silenzioso.
- **Score di Chroma**: distinguere distanza da similarità. Gli score di e5 si concentrano in una
  fascia alta e stretta: le soglie vanno **calibrate empiricamente** (PLAN fase 2), non indovinate.
- **Test unitari senza LLM reale**: usare fake chat model di `langchain_core`. Le chiamate reali
  stanno solo nei test marcati `@pytest.mark.llm`.
- **Costi**: in sviluppo usare il modello economico configurato in `.env`. L'evaluation completa
  moltiplica le chiamate (agente + giudice): non lanciarla senza conferma dell'utente.
- **Colab**: il notebook deve funzionare con "Esegui tutto" su un runtime pulito. Ogni path è
  relativo alla root del repo; niente dipendenze da file locali non versionati.
