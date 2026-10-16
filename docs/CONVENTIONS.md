# Convenzioni e insidie del progetto

Appunti che tengo aggiornati mentre lavoro. Qui ci sono le regole che mi sono dato, il
principio che guida l'architettura e soprattutto le **insidie** delle librerie che uso: le
cose su cui ho sbagliato o che mi hanno fatto perdere tempo, scritte per non ripeterle.

Le decisioni vere e proprie stanno in `DECISIONS.md`, la specifica in `SPEC.md`, il piano in
`PLAN.md`.

## Due regole di metodo

**1. Non fidarsi della memoria sulle API.** LangChain 1.x, RAGAS 0.4 e DeepEval 4.x hanno
cambiato API rispetto a quasi tutto il materiale che si trova online. Prima di usare una
funzione di queste librerie la verifico sulla documentazione o ispezionando il pacchetto
installato:

```bash
uv run python -c "import inspect, X; print(inspect.signature(X.funzione))"
```

Ogni scoperta rilevante finisce in `DECISIONS.md`. Questa regola mi ha salvato diverse volte
e una volta l'ho dimenticata, con il risultato di tre firme sbagliate scoperte solo eseguendo
il notebook.

**2. Ogni scelta architetturale va motivata.** `DECISIONS.md` usa un formato ADR sintetico:
contesto, decisione, alternative scartate, conseguenze. È la materia prima della relazione, e
la valutazione premia le motivazioni più del funzionamento. Una decisione senza alternative
scartate non è una decisione, è un'abitudine.

## Il principio architetturale

**Deterministico prima del probabilistico.** L'LLM decide *cosa dire* e *quale tool usare*;
tutto il resto lo calcola il codice. In concreto:

- `sources` viene dai documenti che il retrieval ha davvero restituito, mai da ciò che il
  modello dichiara di aver usato;
- `needs_human` è vero se e solo se il tool di escalation è stato invocato con successo;
- la `confidence` proposta dal modello viene limitata da regole deterministiche sulla qualità
  del retrieval;
- la data corrente arriva da un `Clock` iniettato, mai da `datetime.now()` sparso nel codice.

Dettagli in `SPEC.md` §5.

## Convenzioni di codice

- Nomi in **inglese**: `snake_case` per funzioni, variabili e moduli, `CamelCase` per le
  classi, `UPPER_SNAKE_CASE` per le costanti.
- **Docstring su ogni funzione, metodo e classe**, stile Google (Args / Returns / Raises).
  Anche sulle funzioni private e sugli helper dei test.
- Type hints sempre; modelli dati con Pydantic v2.
- Quello che legge il cliente — knowledge base, prompt, risposte — è in **italiano**. Nomi,
  docstring e messaggi di commit in **inglese**: è lo standard dell'ecosistema Python e non
  volevo un codice mezzo e mezzo.
- Nessun segreto nel codice: tutta la configurazione passa da `src/greenthumb/config.py`, che
  legge `.env` in locale e i Secrets su Colab.
- Funzioni piccole e testabili, I/O ai bordi e logica pura al centro.
- Commit piccoli, Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`,
  `refactor:`). Mai committare `.env`, il vector store o le cache.

## Insidie note

Questa è la sezione che mi è servita di più. Ogni voce mi è costata del tempo.

- **LangChain 1.x**: si usa `langchain.agents.create_agent`. `AgentExecutor`,
  `initialize_agent` e il vecchio `create_react_agent` con i prompt da LangChain Hub sono
  API legacy, e sono quelle che trovi in nove tutorial su dieci.
- **Embedding e5**: `multilingual-e5-base` vuole i prefissi `"query: "` sulle query e
  `"passage: "` sui documenti. La documentazione dice che senza di essi la qualità del
  retrieval crolla in modo silenzioso. **L'ho misurato quattro volte e il crollo non si
  verifica** sul mio corpus (ADR-022, ADR-041, ADR-046): i prefissi li tengo comunque perché
  sono l'uso documentato del modello e non costano nulla, ma vale la lezione generale —
  un'insidia ereditata va misurata sui propri dati prima di trattarla come critica.
- **Score di Chroma**: distinguere la distanza dalla similarità. Gli score di e5 si
  concentrano in una fascia alta e stretta, quindi le soglie vanno **calibrate sui dati**, non
  indovinate (ADR-040: la separazione fra query pertinenti e fuori tema è di appena +0.0132).
- **Test unitari senza LLM**: i fake chat model di `langchain_core` non bastano a pilotare
  questo agente (ADR-049). Le chiamate reali stanno solo nei test marcati `@pytest.mark.llm`,
  esclusi da `make test`.
- **Costi**: in sviluppo uso il modello economico configurato nel `.env`. L'evaluation
  completa moltiplica le chiamate, perché gira l'agente più tre giudici: circa 300 chiamate
  per esecuzione.
- **Colab**: il notebook deve funzionare con «Esegui tutto» su un runtime pulito. Ogni
  percorso è relativo alla radice del repository, e niente dipende da file locali non
  versionati.
- **Librerie che fanno I/O all'import**: `import deepeval` chiama `load_dotenv()` come
  effetto collaterale e installa un plugin pytest. I miei test unitari sono diventati rossi
  nel momento esatto in cui è comparso un `.env`, senza che cambiasse una riga di codice
  (ADR-025, ADR-044). L'isolamento dei test dalla configurazione locale va imposto, non dato
  per scontato.

## Comandi

```bash
make setup      # uv sync + installa gli hook di pre-commit
make data       # genera orders.json e valida la knowledge base
make index      # (ri)costruisce il vector store Chroma
make test       # test unitari, nessuna chiamata LLM
make test-llm   # test di integrazione con LLM reale (richiede .env)
make lint       # ruff check + ruff format --check
make eval       # evaluation completa (costa: chiede conferma)
make eval-smoke # una conversazione sola attraverso tutta la pipeline
make serve      # avvia l'API su http://localhost:8000
```

Tutto passa da `uv run`; non uso `pip install` direttamente nel progetto.
