# Metodo di lavoro

Il progetto è stato costruito in nove fasi, ciascuna chiusa da una **Definition of Done**
verificabile: finché i suoi controlli non passano, la fase non è chiusa e non se ne apre la
successiva. L'ordine è quello imposto dalle dipendenze reali — dati e indicizzazione, tool,
loop ReAct, memoria, output strutturato, evaluation, API, consegna — perché ogni anello
poggia sul precedente: non si calibra una soglia di rilevanza senza la knowledge base
definitiva, e non si misura un agente che non esiste ancora.

Due scelte di metodo hanno pesato più delle altre.

**La verifica delle API precede il codice che le usa.** LangChain 1.x, RAGAS 0.4 e DeepEval 4.x
hanno interfacce diverse da quasi tutto il materiale pubblicato, quindi la fase 0 esiste solo
per provare su pacchetto installato ciò che l'architettura dà per scontato. Il rischio più
grave del progetto — che il passo di output strutturato nascondesse i metadati dei tool,
rendendo irrealizzabile il livello deterministico su cui tutto si regge — è stato sciolto lì,
con uno spike, prima di scrivere una riga di codice di produzione (ADR-027).

**Ogni scelta non ovvia è registrata man mano**, con contesto, alternative scartate e
conseguenze, in `DECISIONS.md`. Non è documentazione a posteriori: diversi numeri di questo
progetto — le soglie di retrieval, la soglia di summarization, il limite di iterazioni —
esistono perché una misura ha contraddetto l'ipotesi di partenza, e il registro conserva
entrambe.

| Fase | Cosa produce | Chiusa quando |
|---|---|---|
| 0 | ambiente e API verificate | `make setup`, `make lint`, `make test` passano; nessun segreto nel repo |
| 1 | knowledge base e ordini sintetici | `make data` verde, ≥35 documenti e ≥24 ordini, campione riletto a mano |
| 2 | vector store e soglie calibrate | hit@4 ≥ 0.9 sulle query pertinenti, soglie motivate con i numeri |
| 3 | i tre tool | test verdi, ogni tool invocabile da uno script dimostrativo |
| 4 | agente ReAct | l'esempio della traccia risolto su entrambe le parti della domanda |
| 5 | memoria a breve termine | la summarization scatta *e* le entità del primo turno sopravvivono |
| 6 | contratto di risposta | schema valido sul 100% dei turni, una `chat()` pubblica unica |
| 7 | evaluation | trace, punteggi e `summary.md` con confronto prima/dopo |
| 8 | API | `make serve` e i curl funzionano da zero seguendo solo il README |
| 9 | notebook di consegna | eseguito end-to-end su Colab con gli output salvati |

---

## Fase 0 — Ambiente e verifica delle librerie

Inizializzazione del repository con le versioni fissate in SPEC §2, `config.py` e `clock.py`
con i rispettivi test, e sette spike in `scripts/spikes/`: `ChatLiteLLM` con e senza tool,
`create_agent` con `response_format` Pydantic per stabilire quale strategia di output
strutturato funziona, un tool con `response_format="content_and_artifact"` per verificare che
l'artifact resti leggibile, il middleware di summarization con il checkpointer, e l'aggancio
dei giudici RAGAS e DeepEval. Gli esiti sono in `DECISIONS.md`, ADR-019 a ADR-028: fra essi un
pin di dipendenza senza cui `import ragas` non funziona, e un vincolo dello schema strict per
cui nessun campo dell'output può avere un default.

## Fase 1 — Dati sintetici

`catalog.yaml` come fonte unica di verità dei 16 prodotti, riletto prima di scrivere il resto
perché tutto ne dipende; 37 documenti Markdown con frontmatter (16 schede, 14 guide, 7 policy),
scritti a lotti variando struttura e registro per evitare documenti-fotocopia; 26 ordini
generati con seed fisso e date relative alla data di business, mai da `datetime.now()`.
`validate_data.py` verifica frontmatter, coerenza fra `doc_id` e percorso, esistenza degli SKU,
allineamento dei prezzi al catalogo, copertura di ogni stato ordine e conformità dell'ordine
dell'esempio. I suoi test corrompono i dati di proposito: un validatore che passa sempre è
indistinguibile dall'assenza di validatore (ADR-037).

## Fase 2 — Indicizzazione e retrieval

`kb_loader.py` e `retrieval.py`, chunking guidato dagli heading, embedding locali con i
prefissi richiesti dal modello, Chroma persistente. Le soglie non sono state indovinate:
`probe_retrieval.py` le calibra su 20 query — 12 con documento atteso noto, 8 fuori tema —
formulate senza riusare le frasi dei documenti, perché usarle gonfierebbe gli score e
calibrerebbe su una situazione irreale. Risultati e tabelle complete in
`RETRIEVAL_CALIBRATION.md`; la separazione misurata fra query pertinenti e non pertinenti è di
appena +0.0132, e la conseguenza architetturale è registrata in ADR-040: la soglia non è un
confine affidabile e non va trattata come tale.

## Fase 3 — I tre tool

`orders_repository.py`, `escalations_repository.py` e i tool di ricerca nella knowledge base,
stato ordine ed escalation, con descrizioni scritte per il modello e casi limite gestiti senza
eccezioni verso l'agente. I test coprono caso nominale, ordine inesistente, identificatori
malformati ma normalizzabili, assenza di documenti rilevanti, idempotenza dell'escalation e
date relative con un clock congelato.

## Fase 4 — Agente ReAct

`prompts.py` con la data di business iniettata a ogni chiamata al modello, `agent.py` con i tre
tool, il limite di iterazioni e la risposta di ripiego. I criteri di escalation non sono scritti
a mano nel prompt ma generati dall'enum che il tool accetta, con un test che asserisce la
coincidenza dei due insiemi: un criterio presente nell'enum e assente dal prompt sarebbe
irraggiungibile, e nessun test di integrazione lo scoprirebbe se non per caso (ADR-052).

## Fase 5 — Memoria a breve termine

Middleware di summarization con prompt dedicato, checkpointer con `thread_id = session_id`, e
log dei token che hanno fatto scattare la soglia. La fase ha prodotto due scoperte: la soglia
si confronta con il totale che il provider riporta per l'intera richiesta, schemi dei tool
inclusi, e il valore inizialmente previsto era *sotto* il pavimento misurato della prima
chiamata (ADR-056); e una memoria che funziona può non servire a nulla, se il prompt non
dichiara la storia della conversazione conoscenza legittima (ADR-057).

## Fase 6 — Contratto di risposta

`schemas.py` e `response.py`: intersezione fra le fonti citate e quelle realmente recuperate,
`needs_human` derivato dal registro delle escalation, cap della confidence sugli score,
ripiego su errore di formato. Testato con trace costruite a mano e nessuna chiamata LLM, perché
un fake chat model non è in grado di pilotare questo agente (ADR-049). `service.py` espone la
`chat()` pubblica che API ed evaluation condividono.

## Fase 7 — Evaluation

Dataset di 20 conversazioni riletto *prima* dell'esecuzione, perché determina tutto il resto, e
verificato da 17 test contro la knowledge base e gli ordini reali: un `doc_id` sbagliato non
solleverebbe nulla, abbasserebbe una metrica in silenzio e il report attribuirebbe all'agente un
difetto del dataset. Runner con salvataggio delle trace, metriche RAGAS, DeepEval e
deterministiche, analisi dei casi peggiori, un intervento correttivo misurato e la seconda
esecuzione a confronto. Commento e numeri in `eval/results/summary.md`.

## Fase 8 — API

`api.py` con inizializzazione nel lifespan, contratto a quattro campi, `session_id` restituito
in un header per non alterare il JSON, e ripiego osservabile sugli errori del provider. Testata
con client di prova e agente simulato, poi contro un server reale seguendo solo il README.

## Fase 9 — Notebook di consegna

Notebook generato da `scripts/build_notebook.py`, non scritto a mano, con la relazione tecnica
nelle celle Markdown e gli output salvati, così che si legga senza essere rieseguito e senza
spendere chiamate al modello. Resta da eseguire su un runtime Colab pulito: è il controllo che
chiude la fase.
