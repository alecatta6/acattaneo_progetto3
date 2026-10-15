# Piano di lavoro

L'ordine segue quello richiesto dalla traccia: dati e indicizzazione → tool → loop ReAct →
memoria → structured output → evaluation → API. Ogni fase termina con una Definition of Done
(DoD) verificabile. Claude Code si ferma a fine fase e attende approvazione.

Stato: aggiornare la casella di ogni fase quando l'utente la approva.

---

## [x] Fase 0 — Bootstrap e spike tecnico ✅ completata

**Obiettivo**: ambiente funzionante e API delle librerie verificate *prima* di scrivere il codice
vero. Questa fase esiste per evitare di costruire su API che non esistono più.

Task:
1. Inizializzare il repo: `uv init`, `pyproject.toml` con le versioni di SPEC §2, `.gitignore`
   (`.env`, `vector_store/`, `escalations.jsonl`, cache), `.env.example`, `Makefile`,
   configurazione ruff (incluse le regole docstring `D` con convenzione Google e naming `N`).
2. `config.py` e `clock.py` con test.
3. Spike in `scripts/spikes/` (non codice di produzione, da cancellare o archiviare a fine fase):
   - `ChatLiteLLM` con il modello configurato: una chiamata semplice e una con tool.
   - `create_agent` con un tool fittizio e `response_format` Pydantic: verificare quale
     strategia di structured output funziona col modello scelto.
   - Tool con `response_format="content_and_artifact"`: verificare che l'artifact sia leggibile
     dai messaggi restituiti dall'agente.
   - Middleware di summarization: nome della classe, parametri, comportamento con checkpointer.
   - RAGAS 0.4 e DeepEval 4.x: import e firma delle metriche previste in SPEC §10.3, configurazione
     del modello giudice via LiteLLM.
4. Registrare i risultati degli spike in `docs/DECISIONS.md`.

DoD:
- `make setup`, `make lint`, `make test` passano.
- DECISIONS.md contiene le firme verificate e le eventuali deviazioni dalla SPEC.
- Nessuna chiave nel repo (`git grep -i "api_key"` restituisce solo nomi di variabili).

---

## [x] Fase 1 — Dati sintetici ✅ completata (revisione utente effettuata)

**Obiettivo**: knowledge base e ordini realistici, coerenti tra loro, validati automaticamente.

Task:
1. `data/catalog.yaml` con 16 prodotti (SPEC §4.2). **Fermarsi e mostrarlo all'utente** prima di
   scrivere le schede: tutto il resto ne dipende.
2. 16 schede prodotto, 12 guide, 7 policy (SPEC §4.3). Scrivere a lotti (prima le policy, poi
   prodotti, poi guide), variando struttura e registro per evitare documenti-fotocopia.
3. `scripts/generate_orders.py` (seed fisso, relativo alla business date) → `data/orders.json`.
4. `scripts/validate_data.py`: frontmatter completo e valido, `doc_id` coerente col path, SKU
   esistenti nel catalogo, prezzi coerenti, ogni stato ordine coperto ≥2 volte, ordine 1042
   conforme alla traccia, lunghezza documenti nel range, `guides/bulbi_autunnali.md` presente.
5. Test su generatore (determinismo: due esecuzioni → file identico) e validatore.

DoD:
- `make data` passa senza errori; ≥35 documenti e ≥24 ordini.
- L'utente ha rivisto un campione di documenti (almeno 1 per tipo) e il catalogo.

---

## [x] Fase 2 — Indicizzazione e retrieval ✅ completata

**Obiettivo**: vector store costruito e soglie di rilevanza calibrate su dati reali.

Task:
1. `kb_loader.py`, `retrieval.py` (SPEC §6), `scripts/build_index.py`, `make index`.
2. `scripts/probe_retrieval.py`: ~20 query di prova (12 con documento atteso noto, 8 fuori
   tema o senza risposta nella KB). Stampare top-k con score e calcolare hit@1 / hit@4.
3. Calibrazione: scegliere `RETRIEVAL_SCORE_LOW` e `RETRIEVAL_SCORE_HIGH` osservando la
   distribuzione degli score delle query pertinenti rispetto a quelle non pertinenti. Salvare il
   grafico o la tabella in `docs/` e le soglie in config.
4. Test unitari su chunking (metadati propagati, prefisso titolo, niente chunk vuoti) e
   sull'applicazione dei prefissi e5.

DoD:
- hit@4 ≥ 0.9 sulle query pertinenti; le query fuori tema scendono sotto la soglia bassa
  (o sono documentate le eccezioni).
- Decisione su chunking e soglie registrata in DECISIONS.md con i numeri.

---

## [x] Fase 3 — Tool ✅ completata

**Obiettivo**: tre tool con contratti espliciti e casi limite coperti, testati senza LLM.

Task:
1. `orders_repository.py` e i tre tool (SPEC §7), con descrizioni curate per il modello.
2. Test per ogni tool: caso nominale, ordine inesistente, ID malformato/normalizzabile
   ("#1042", "ordine 1042"), nessun documento rilevante, idempotenza escalation, date relative
   corrette con `FrozenClock`.

DoD:
- Test verdi; ogni tool invocabile singolarmente da uno script demo.

---

## [x] Fase 4 — Agente ReAct ✅ completata

**Obiettivo**: loop ReAct funzionante con orchestrazione multi-tool.

Task:
1. `prompts.py` (system prompt con business date dinamica, SPEC §8) e `agent.py`.
2. Limite di iterazioni e fallback.
3. Test di integrazione `@pytest.mark.llm`: esempio della traccia (entrambi i tool invocati),
   escalation su richiesta esplicita, domanda fuori scope senza escalation, richiesta ambigua →
   domanda di chiarimento.
4. Test unitari del wiring con fake chat model.

DoD:
- L'esempio della traccia produce una risposta corretta su entrambe le parti della domanda.
- Scelte sul prompt (struttura, criteri di escalation) motivate in DECISIONS.md.

---

## [x] Fase 5 — Memoria a breve termine ✅ completata

**Obiettivo**: conversazioni multi-turn con summarization verificata.

Task:
1. `memory.py`: middleware di summarization con prompt personalizzato (SPEC §9), checkpointer,
   `thread_id = session_id`.
2. Test di integrazione: conversazione che supera la soglia; il numero d'ordine del turno 1 resta
   utilizzabile; il riassunto contiene le entità richieste.
3. Loggare quando scatta la summarization (utile per la demo nel notebook).

DoD:
- Test di memoria verdi; strategia e soglie motivate in DECISIONS.md.

---

## [x] Fase 6 — Structured output e assemblaggio della risposta ✅ completata

**Obiettivo**: ogni turno restituisce una `ChatResponse` valida con campi deterministici.

Task:
1. `schemas.py` e `response.py` (SPEC §5): intersezione sources, regola `needs_human`, cap della
   confidence, fallback su errori di parsing.
2. Test unitari esaustivi di `response.py` con trace costruite a mano (nessun LLM): source
   inventata dall'LLM scartata, escalation → `needs_human=true` e `confidence="low"`, domanda
   solo-ordini senza cap, retrieval vuoto → `low`.

DoD:
- 100% delle risposte dei test di integrazione valide rispetto allo schema.
- Una funzione pubblica `chat(message, session_id) -> ChatResponse` usata da API ed evaluation
  (`ChatService.chat` in `service.py`; `chat_detailed` restituisce in più i contesti recuperati
  e i tool invocati, che servono all'evaluation e all'header `X-Fallback` dell'API).

---

## [x] Fase 7 — Evaluation ✅ completata (revisione utente effettuata)

**Obiettivo**: misurare l'affidabilità e commentare i risultati.

Task:
1. `eval/conversations.jsonl` (20 conversazioni, SPEC §10.1 e ADR-016/062). **Fermarsi e farlo rivedere**
   prima di eseguire: il dataset determina tutto il resto.
2. Runner con salvataggio delle trace; metriche RAGAS, DeepEval e deterministiche.
3. Prima esecuzione completa (chiedere conferma: ha un costo), `summary.md`.
4. Analisi dei 3 casi peggiori → almeno un intervento correttivo (prompt, soglie, chunking) →
   seconda esecuzione → confronto prima/dopo.
5. Opzionale: esperimento di re-ranking misurato.

DoD:
- `eval/results/` contiene trace, punteggi e `summary.md` con commento e confronto prima/dopo.

---

## [x] Fase 8 — API ✅ completata

**Obiettivo**: agente esposto via FastAPI con istruzioni di avvio.

Task:
1. `api.py` (SPEC §11) con lifespan, header `X-Session-Id`, gestione errori.
2. Test con `TestClient` (agente mockato): contratto a 4 campi, header di sessione, 422 su input
   non valido, fallback su errore del provider.
3. README: installazione, `.env`, `make index`, `make serve`, esempi curl (incluso multi-turn).

DoD:
- `make serve` + curl dell'esempio della traccia funzionano da zero seguendo solo il README.

---

## [ ] Fase 9 — Notebook di consegna e relazione 🔍 REVIEW

**Obiettivo**: notebook Colab pubblico, autosufficiente, che contiene la relazione.

Task:
1. `notebooks/greenthumb_delivery.ipynb` secondo SPEC §13; uvicorn in thread per la demo API.
2. Relazione nelle celle Markdown: scelte architetturali, memoria, analisi dell'evaluation,
   limiti e sviluppi futuri. Tono tecnico, sintetico, in italiano.
3. Verifica su runtime Colab pulito (eventualmente tramite il Colab MCP server): "Esegui tutto"
   senza errori; output salvati.
4. Aggiornare la tabella di tracciabilità SPEC §1 e controllare ogni requisito.

DoD:
- Notebook eseguito end-to-end su Colab con output salvati.
- Tutti i requisiti R1–R10 verificati.
