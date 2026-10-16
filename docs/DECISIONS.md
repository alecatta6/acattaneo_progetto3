# Registro delle decisioni architetturali

Formato: contesto → decisione → alternative scartate → conseguenze.
Questo file è la fonte primaria della relazione tecnica. Aggiungere una voce per ogni scelta non
ovvia, inclusi gli esiti degli spike della fase 0 e i numeri delle calibrazioni.

---

## ADR-001 — Sviluppo in repository locale, consegna via notebook Colab

- **Contesto**: la consegna è un link Colab; la traccia chiede anche un repository.
- **Decisione**: sviluppo in un repository Python versionato e testato; il notebook clona il
  repo e ne esegue le parti, contenendo la relazione.
- **Alternative scartate**: sviluppo interamente in Colab (niente git e test, sessioni
  effimere); celle `%%writefile` (codice poco manutenibile).
- **Conseguenze**: codice testabile e modulare; serve verificare il notebook su runtime pulito.

## ADR-002 — Deterministico prima del probabilistico nella risposta

- **Contesto**: `sources`, `needs_human` e `confidence` generati liberamente dall'LLM possono
  essere inventati o incoerenti con le azioni svolte.
- **Decisione**: `sources` filtrate sui documenti realmente recuperati; `needs_human` derivato
  dall'invocazione del tool di escalation; `confidence` con cap basato sugli score del retrieval.
- **Alternative scartate**: output interamente generato dall'LLM.
- **Conseguenze**: impossibili fonti inesistenti o flag incoerenti; metriche deterministiche
  gratuite nell'evaluation.

## ADR-003 — Data di business simulata

- **Contesto**: le risposte dipendono dalla data (consegne, stagionalità) e il notebook verrà
  eseguito in una data ignota.
- **Decisione**: `Clock` iniettato; default `FrozenClock(2026-10-12)`, configurabile.
- **Alternative scartate**: data reale (ordini ed evaluation perdono validità nel tempo); ordini
  rigenerati a ogni esecuzione (ground truth instabile).
- **Conseguenze**: sistema riproducibile; la stagione "corrente" è autunno per costruzione.

## ADR-004 — Memoria a breve termine: summarization

- **Contesto**: nel customer care le entità citate presto (numero d'ordine) servono molti turni
  dopo.
- **Decisione**: summarization con soglia in token e ultimi N messaggi integri, prompt che
  preserva entità.
- **Alternative scartate**: trimming (perde le entità iniziali); trimming + stato strutturato
  (più robusto ma più complesso, citato come evoluzione).
- **Conseguenze**: una chiamata LLM in più oltre soglia; verificata con test ed evaluation
  conversazionale.

## ADR-005 — Embedding locali multilingue

- **Contesto**: KB in italiano, notebook eseguito da terzi, nessuna GPU necessaria.
- **Decisione**: `intfloat/multilingual-e5-base` in locale.
- **Alternative scartate**: embedding via API (secondo provider, costo per chunk); modelli
  solo-inglese.
- **Conseguenze**: nessun costo di indicizzazione; attenzione ai prefissi `query:`/`passage:`
  e alla calibrazione delle soglie.

## ADR-006 — `doc_id` con estensione, rappresentazione unica

- **Contesto**: la SPEC definiva `doc_id` senza estensione (§4.3) ma lo usava con estensione in
  `sources` (§5) e in `expected_sources` (§10.1). Due rappresentazioni della stessa entità.
- **Decisione**: `doc_id` include sempre l'estensione (`guides/bulbi_autunnali.md`), identico in
  frontmatter, metadati dei chunk, `sources` ed `expected_sources`.
- **Alternative scartate**: funzione di conversione in un punto unico (un'occasione in più di
  sbagliare in silenzio: un mismatch di suffisso porta `source_recall` a 0 senza alcun errore);
  due campi distinti nel frontmatter (ridondanza da mantenere a mano su 35 file).
- **Conseguenze**: nessuna conversione in nessun punto del sistema. SPEC §4.3 aggiornata.

## ADR-007 — `confidence` disaccoppiata da `needs_human`

- **Contesto**: la SPEC imponeva `cap = low` a ogni escalation.
- **Decisione**: l'escalation non influisce sulla confidence. `confidence` qualifica la risposta
  (ed è limitata solo dalla qualità del retrieval); `needs_human` ne governa l'instradamento.
- **Alternative scartate**: override assoluto a `low` (più semplice, ma confonde "non sono sicuro"
  con "serve un operatore": un rimborso correttamente riconosciuto come fuori termine è una
  risposta *giusta*, e marcarla `low` penalizza proprio i casi gestiti bene nella metrica GEval);
  cap intermedio a `medium` (terza regola da giustificare, senza un beneficio chiaro).
- **Conseguenze**: i due campi restano ortogonali e indipendentemente misurabili nell'evaluation.

## ADR-008 — `needs_human` con semantica di sessione

- **Contesto**: `needs_human` legato al singolo turno tornava `false` al turno successivo a
  un'escalation, pur con il ticket ancora aperto — in contrasto con l'idempotenza per
  sessione+motivo dell'escalation (§7).
- **Decisione**: `needs_human = true` finché la sessione ha almeno un ticket aperto.
- **Alternative scartate**: semantica di turno (lettera della SPEC originale; più semplice, ma
  semanticamente povera per un customer care reale).
- **Conseguenze**: serve uno stato di sessione, che resta **deterministico** perché derivato dal
  registro delle escalation e non da un giudizio dell'LLM (ADR-002 è salvo). `expected_needs_human`
  va impostato di conseguenza in tutte le conversazioni multi-turn del dataset. **Da rivedere** se
  l'esempio della traccia mostrasse `needs_human: false` dopo un'escalation.

## ADR-009 — Header `X-Fallback` sulle risposte di ripiego

- **Contesto**: §11 impone status 200 anche sugli errori del provider, per non rompere il
  contratto a 4 campi della traccia. Così però un'interruzione del provider è invisibile.
- **Decisione**: il JSON resta invariato; un header `X-Fallback: true` segnala il ripiego.
- **Alternative scartate**: solo log (l'osservabilità resta lato server); status non-200 (rompe
  il contratto richiesto dalla traccia).
- **Conseguenze**: coerente con la scelta già fatta per `X-Session-Id`. Costo implementativo nullo.

## ADR-010 — Modello giudice separato, validato in modo pigro

- **Contesto**: un giudice diverso dal modello valutato riduce il bias di auto-valutazione, ma un
  requisito rigido rischia di bloccare "Esegui tutto" su Colab.
- **Decisione**: `GREENTHUMB_EVAL_MODEL` è obbligatorio, ma validato **solo** quando l'evaluation
  viene effettivamente eseguita, non all'import del pacchetto.
- **Alternative scartate**: ripiego silenzioso sul modello dell'agente (rischio di pubblicare
  risultati auto-valutati senza accorgersene); rinuncia al giudice separato (si perde un punto
  di merito facile).
- **Conseguenze**: il notebook carica i risultati già salvati (§13) e gira con il solo segreto
  dell'agente; chi rilancia l'evaluation riceve un errore esplicito. Con OpenAI come provider
  (ADR-015) agente e giudice condividono la stessa chiave: nessun secondo provider da configurare.

## ADR-011 — Nessuna escalation al primo ordine non trovato

- **Contesto**: §8 richiedeva l'escalation solo dopo un secondo tentativo con numero confermato,
  ma §10.1 collocava "ordine inesistente" fra gli `edge_cases`, tipicamente mono-turno.
- **Decisione**: primo tentativo → `found: false` e invito a verificare il numero, con
  `needs_human = false`. L'escalation `order_not_found` scatta solo al secondo tentativo confermato.
- **Alternative scartate**: escalation immediata (genera ticket per ogni errore di battitura).
- **Conseguenze**: la riga `edge_cases` della tabella §10.1 è stata annotata per non lasciare
  l'aspettativa ambigua a chi scriverà il dataset in Fase 7.

## ADR-012 — Limite di iterazioni ReAct a 8

- **Contesto**: §8 proponeva 6. Se lo structured output è realizzato come tool call
  (*ToolStrategy*), consuma un'iterazione: un turno multi-tool legittimo arriva a 5–6 passi.
- **Decisione**: 8, con margine prudenziale.
- **Alternative scartate**: 6 (rischio di troncare turni validi e falsare l'evaluation con
  fallback spuri); fissarlo dopo lo spike (rimanda una scelta il cui costo di errore è basso).
- **Conseguenze**: in caso di loop patologico si spendono al più due chiamate in più. Lo spike n.1
  misurerà il consumo reale e il valore verrà confermato o corretto qui.

## ADR-013 — Prefisso `GREENTHUMB_` su tutte le variabili di progetto

- **Contesto**: §12 mescolava nomi prefissati e generici (`LLM_MODEL`, `RETRIEVAL_TOP_K`).
- **Decisione**: prefisso su tutte le variabili di progetto; fanno eccezione le chiavi dei
  provider, il cui nome è imposto dall'SDK.
- **Alternative scartate**: nessun prefisso (collisione concreta con l'ambiente condiviso di Colab).
- **Conseguenze**: `.env.example` e i Secrets di Colab usano i nomi prefissati.

## ADR-014 — Python 3.12 gestito da uv

- **Contesto**: la macchina di sviluppo ha solo Python 3.14.7 (Homebrew); Colab gira su 3.12.
- **Decisione**: `uv python install 3.12`, interprete isolato per il progetto,
  `requires-python = "==3.12.*"`.
- **Alternative scartate**: 3.14 (tecnicamente possibile — `litellm` ammette `<3.15` e torch 2.14
  ha ruote cp314 — ma il lockfile verrebbe risolto per un interprete diverso da quello di
  consegna); Homebrew `python@3.12` (stato di sistema modificabile da `brew upgrade`).
- **Conseguenze**: `uv.lock` e `requirements.txt` allineati al runtime di consegna.

## ADR-015 — OpenAI come provider dell'agente e del giudice

- **Contesto**: la scelta del provider determina la strategia di structured output e l'aggancio
  dei giudici RAGAS/DeepEval.
- **Decisione**: OpenAI via LiteLLM.
- **Alternative scartate**: Anthropic e Gemini (entrambi validi, ma con uno strato di traduzione
  in più da verificare attraverso LiteLLM).
- **Conseguenze**: probabile *ProviderStrategy* con `response_format` nativo, che non consuma
  iterazioni del ciclo ReAct; RAGAS 0.4 (che dipende da `openai>=1.0.0`) e DeepEval 4.x hanno
  entrambi OpenAI come percorso nativo, riducendo il lavoro di wiring del giudice.

## ADR-016 — Dataset di evaluation a 20 conversazioni

- **Contesto**: l'enum `reason` dell'escalation ha 7 valori, coperti da sole 2 conversazioni.
- **Decisione**: 20 conversazioni; `escalation` e `multi_tool` salgono a 3 ciascuna.
- **Alternative scartate**: ribilanciare a somma costante togliendo `product_info` e
  `agronomic_advice` (il retrieval su scheda prodotto è la parte meno rischiosa, ma resta una
  categoria richiesta); distribuzione originale (copertura insufficiente dove il sistema cede).
- **Conseguenze**: ogni riesecuzione dell'evaluation costa 2 conversazioni in più (agente + giudice).

## ADR-017 — Knowledge base completa in Fase 1, senza fetta verticale

- **Contesto**: la Fase 1 richiede 35 documenti italiani scritti a mano *prima* che l'agente
  esista. Si era valutato di ridurre la KB per arrivare prima end-to-end.
- **Decisione**: si mantiene l'ordine del PLAN, con KB completa in Fase 1.
- **Alternative scartate**: fetta verticale con ~10 documenti (anticipa i rischi architetturali,
  ma obbliga a calibrare le soglie di retrieval due volte, perché soglie tarate su 10 documenti
  non valgono su 35); spike end-to-end esteso in Fase 0 (mezza giornata di lavoro usa-e-getta).
- **Conseguenze**: il rischio architetturale ricade interamente sugli spike di Fase 0; lo spike
  n.1 verifica structured output e artifact con un tool fittizio, prima di investire nei contenuti.
  La calibrazione delle soglie avviene una volta sola, su dati definitivi.

## ADR-018 — Dipendenze e telemetria: due vincoli non negoziabili

- **Contesto**: due dettagli emersi ispezionando i metadati delle release su PyPI.
- **Decisione**: (a) installare `langchain-huggingface[full]`, perché nella 1.2.2
  `sentence-transformers` e `transformers` sono dichiarati **solo** sotto l'extra `full`: con
  un'installazione nuda `HuggingFaceEmbeddings` fallisce all'import; (b) disattivare esplicitamente
  la telemetria di DeepEval, perché un notebook di consegna non deve caricare i risultati di
  valutazione su un servizio cloud terzo senza che chi lo esegue lo sappia.
- **Conseguenze**: l'extra `full` porta con sé `transformers>=5.0.0,<6`, major version su cui gran
  parte del materiale online è obsoleto — vale la regola 1 di `docs/CONVENTIONS.md`. Si noti anche che
  `langchain-litellm` 0.7.2 non dichiara **alcuna** dipendenza (né `langchain-core` né `litellm`):
  nessun resolver ci proteggerà da un disallineamento, che va verificato a mano.

## ADR-019 — Pin di `langchain-community` a 0.3.31 per far funzionare RAGAS

- **Contesto**: con lo stack di SPEC §2 risolto liberamente, `import ragas` fallisce:
  `ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'`.
  Causa: `ragas/llms/base.py` importa `ChatVertexAI` e `VertexAI` da `langchain_community` in modo
  **incondizionato** (riga 12), ma `langchain-community` 0.4.x ha svuotato `chat_models/` di tutti
  gli integratori di provider. RAGAS dichiara `langchain-community` **senza alcun pin**, quindi il
  resolver sceglie 0.4.2 e il pacchetto risulta inutilizzabile. Non è aggirabile ignorando il
  modulo: la catena parte da `ragas/__init__.py`, quindi *qualsiasi* import di ragas esplode.
- **Decisione**: pin esplicito `langchain-community==0.3.31`. È l'ultima release che contiene
  ancora `chat_models/vertexai.py` **ed** è l'unica 0.3.x il cui vincolo su langchain-core
  (`<2.0.0,>=0.3.78`) ammette il core 1.6.3 richiesto da langchain 1.4.2. Le 0.3.x precedenti
  richiedono `langchain-core<1.0.0` e vanno in conflitto diretto.
- **Alternative scartate**: shim fittizio del modulo mancante (funziona, ma è fragile e
  indifendibile in un notebook di consegna); downgrade di RAGAS (ci riporterebbe a un'API ancora
  più lontana da quella documentata); rinuncia a RAGAS (è un requisito d'esame, R6).
- **Conseguenze**: `langchain-community` scende da 0.4.2 a 0.3.31 e rientra `langchain-classic`
  fra le dipendenze rimosse; verificato che `create_agent`, `ChatLiteLLM`, `Chroma` e
  `HuggingFaceEmbeddings` continuano a importarsi correttamente dopo il downgrade. Il pin è
  **fragile per costruzione**: dipende da un modulo deprecato che prima o poi sparirà. Va
  rivisitato a ogni aggiornamento di RAGAS, e citato nella relazione come esempio concreto di
  rischio di catena delle dipendenze in un ecosistema in rapida evoluzione.

## ADR-020 — RAGAS: usare `ragas.metrics.collections`, non `ragas.metrics`

- **Contesto**: importando `Faithfulness` e `LLMContextPrecisionWithReference` da `ragas.metrics`,
  la 0.4.3 emette un `DeprecationWarning` esplicito: quel percorso sarà rimosso in v1.0 e il
  sostituto è `ragas.metrics.collections`.
- **Decisione**: usare `ragas.metrics.collections` fin da subito.
- **Conseguenze**: conferma la regola 1 di `docs/CONVENTIONS.md` — quasi tutto il materiale online su RAGAS
  usa il percorso deprecato. Le firme esatte delle due metriche restano da verificare nello
  spike n.5 (fase 0, passo 4).

## ADR-021 — Soglie calibrate sulla distanza grezza di Chroma

- **Contesto**: SPEC §6 parla di "score" senza dire quale API usare, e fra le insidie che mi
  ero annotato c'è proprio distinguere distanza da similarità. Spike n.4, nessuna chiamata LLM.
- **Misura**: sulla versione installata le due API sono legate da una relazione esatta,
  `relevance = 1 − distanza` (verificato: distanza 0.0870 → relevance 0.9130; 0.1261 → 0.8739;
  0.1304 → 0.8696). Nessuna normalizzazione esotica di mezzo, in questa versione.
- **Decisione**: interrogare con `similarity_search_with_score` (distanza coseno) e convertire
  con una formula esplicita e nostra, `similarity = 1 − distanza`. Le soglie di config sono
  espresse come **similarità**.
- **Alternative scartate**: `similarity_search_with_relevance_scores` (oggi darebbe identici
  risultati, ma la normalizzazione è interna alla libreria e può cambiare in un aggiornamento,
  spostando silenziosamente soglie che avremo calibrato con cura).
- **Conseguenze**: le soglie restano ancorate a un numero che dipende solo dall'embedding, non
  dalla versione di `langchain-chroma`. La formula va documentata nella relazione.

## ADR-022 — Prefissi e5 mantenuti, ma l'effetto misurato è modesto

- **Contesto**: la documentazione di e5 avverte che senza i prefissi `query: ` / `passage: `
  "la qualità del retrieval crolla in modo silenzioso". Lo spike n.4 ha misurato l'affermazione.
- **Misura** (4 passaggi in italiano, 3 query pertinenti, 2 fuori tema):

  | | hit@1 | peggior distanza pertinente | miglior distanza fuori tema | separazione |
  |---|---|---|---|---|
  | con prefissi | 3/3 | 0.1304 | 0.2285 | **+0.0981** |
  | senza prefissi | 3/3 | 0.1346 | 0.2260 | **+0.0914** |

- **Esito**: i prefissi aiutano, ma di poco — la separazione migliora di 0.0067, e `hit@1` è
  perfetto in entrambi i casi. **Su questo campione il "crollo" descritto non si riproduce.**
- **Decisione**: usare comunque i prefissi. Sono l'uso documentato del modello, non costano
  nulla, e l'effetto atteso cresce con corpus più grandi e negativi più difficili di questi.
- **Conseguenze**: l'avvertimento va ridimensionato, non ignorato. Il campione è di
  soli 4 documenti con negativi banali (capitali del Giappone, router wifi): va **rimisurato in
  fase 2** sulla KB reale da 35 documenti, dove i distrattori sono altri documenti di giardinaggio
  e quindi molto più insidiosi. Onestà del dato: non è ancora una prova che i prefissi siano
  superflui, ma nemmeno una conferma che siano critici.
- **Nota di calibrazione**: le distanze pertinenti stanno in 0.087–0.135 e le fuori tema in
  0.226–0.272. La fascia è alta e stretta, come previsto: una soglia plausibile cade
  attorno a similarità 0.82–0.83, ma va calibrata sui dati veri in fase 2, non fissata ora.

## ADR-023 — RAGAS: metriche `collections` chiamate per turno, non `evaluate()`

- **Contesto**: spike n.5, introspezione del pacchetto installato, nessuna chiamata LLM.
- **Scoperte**:
  - La classe si chiama `ContextPrecisionWithReference`, **non** `LLMContextPrecisionWithReference`:
    quest'ultimo esiste solo nel percorso deprecato `ragas.metrics`. SPEC §10.3 va letta di
    conseguenza.
  - Le metriche di `ragas.metrics.collections` richiedono il giudice **nel costruttore**
    (`Faithfulness(llm: InstructorBaseRagasLLM, ...)`) ed espongono
    `ascore(user_input, response, retrieved_contexts)` e
    `ascore(user_input, reference, retrieved_contexts)`: parametri espliciti, non un
    `SingleTurnSample`.
  - `ragas.evaluate()` accetta invece `BaseRagasLLM` e metriche vecchio stile: appartiene al
    percorso legacy. I due mondi non si mescolano.
- **Decisione**: usare le metriche di `collections` e invocare `ascore()` per turno, senza
  `evaluate()`. Si sposa con l'architettura già prevista (SPEC §10.2): le metriche leggono le
  trace salvate, turno per turno.
- **Conseguenze**: il giudice si costruisce con
  `ragas.llms.llm_factory(model, provider="openai", client=OpenAI(...))`. `llm_factory` accetta
  anche `cache=DiskCacheBackend()`, che secondo la sua docstring riduce di molto il costo delle
  rivalutazioni ripetute: da valutare in fase 7, dove rieseguiamo l'evaluation prima e dopo
  l'intervento correttivo.

## ADR-024 — DeepEval: test case a `Turn`, telemetria disattivata, giudice come stringa

- **Contesto**: spike n.6, introspezione del pacchetto installato, nessuna chiamata LLM.
- **Scoperte**:
  - `DEEPEVAL_TELEMETRY_OPT_OUT=YES` funziona e va impostata **prima** dell'import:
    `telemetry_opt_out()` restituisce `True`. Risolve il punto (b) di ADR-018.
  - `ConversationalTestCase(turns=[Turn(role=..., content=..., retrieval_context=...,
    tools_called=...)])`: la forma è a oggetti `Turn`, non a stringhe.
  - `KnowledgeRetentionMetric.measure()` accetta un `ConversationalTestCase`, come serve a noi.
  - `GEval(name, evaluation_params=[...], criteria=..., model=...)` accetta `evaluation_params`
    di tipo `SingleTurnParams`; `LLMTestCaseParams` esiste ancora come alias equivalente, quindi
    il materiale online che usa il vecchio nome non si rompe. Esiste anche `ConversationalGEval`
    per criteri multi-turno.
  - `model` accetta una **stringa** oltre a un `DeepEvalBaseLLM`: con OpenAI (ADR-015) non serve
    scrivere alcun wrapper per il giudice.
  - `GEval` usa `top_logprobs=20`: richiede un modello che esponga i logprob. Con OpenAI è
    soddisfatto, ma è un vincolo da ricordare se il giudice cambiasse provider.
- **Decisione**: usare `Turn`/`ConversationalTestCase`, giudice passato come stringa, telemetria
  disattivata all'ingresso del modulo di evaluation.
- **Conseguenze**: nessun wrapper LLM da scrivere né per DeepEval né per RAGAS, perché entrambi
  hanno OpenAI come percorso nativo. È il dividendo concreto di ADR-015.
- **Nota**: DeepEval installa un plugin pytest che stampa `Running teardown with pytest
  sessionfinish...` anche nei test unitari, che con lui non c'entrano nulla. Innocuo, ma se
  dovesse dare fastidio si disattiva con `-p no:deepeval`.

## ADR-025 — Isolare i test unitari dal `.env`, che DeepEval inietta di nascosto

- **Contesto**: i test unitari, verdi fino a quel momento, sono diventati rossi **nel momento
  esatto in cui è comparso un `.env`** nel progetto, senza che una riga di codice cambiasse.
- **Causa**: `import deepeval` chiama `load_dotenv()` come effetto collaterale, riversando
  l'intero `.env` in `os.environ`. DeepEval installa inoltre un plugin pytest che si carica
  automaticamente a ogni esecuzione. Risultato: `Settings(_env_file=None)`, che *disabilita*
  correttamente la lettura del file, non serviva a nulla — i valori erano già nell'ambiente
  reale del processo. Verificato: `'GREENTHUMB_EVAL_MODEL' in os.environ` passa da `False` a
  `True` per il solo `import deepeval`, e `pytest -p no:deepeval` rende i test di nuovo verdi.
- **Perché è grave**: rende i test unitari dipendenti dalla configurazione locale di chi li
  esegue. Due sviluppatori con `.env` diversi ottengono esiti diversi, e la CI (dove `.env` non
  esiste) diverge da entrambi. È esattamente il tipo di accoppiamento invisibile che un test
  dovrebbe escludere per costruzione.
- **Decisione**: doppia difesa. (a) `-p no:deepeval` negli `addopts` di pytest: le metriche
  DeepEval le invochiamo direttamente (ADR-024), il plugin non ci serve. (b) Una fixture
  `autouse` in `tests/conftest.py` che rimuove `GREENTHUMB_*` e le chiavi dei provider
  dall'ambiente prima di ogni test. Verificato che con la sola fixture, e il plugin
  **riattivato a forza**, i test restano verdi.
- **Alternative scartate**: affidarsi al solo `_env_file=None` (è ciò che è appena fallito);
  il solo `-p no:deepeval` (protegge da questo plugin, non dal prossimo pacchetto che chiami
  `load_dotenv()` all'import).
- **Conseguenze**: aggiunto un test di regressione. Lezione generale da citare nella relazione:
  in un ecosistema dove le librerie di valutazione fanno I/O all'import, l'isolamento dei test
  va imposto attivamente, non dato per scontato.

## ADR-026 — Structured output: strategia nativa, e nessun campo opzionale

- **Contesto**: SPEC §5 chiedeva di verificare in fase 0 se il modello supporta `response_format`
  nativo (*ProviderStrategy*) o se serve ripiegare su *ToolStrategy*. Spike n.1.
- **Esito**: **ProviderStrategy**. `create_agent(..., response_format=AgentOutput)` invia lo schema
  JSON nativamente (l'errore diagnostico cita `text.format.schema`, parametro dell'API del
  provider, non una tool call). Conseguenza diretta: **lo structured output non consuma
  un'iterazione del ciclo ReAct e non compare fra i tool invocati**. Su un turno a un tool
  l'unica tool call registrata è quella reale, e lo stato finale conta 4 messaggi.
- **Conseguenza su ADR-012**: il limite di 8 iterazioni è abbondante, non stretto. Resta a 8.
- **Conseguenza su `tool_selection_accuracy`**: la metrica non va depurata da chiamate sintetiche,
  perché non ce ne sono.
- **Vincolo scoperto**: in modalità strict **ogni campo dello schema deve essere obbligatorio**.
  Un campo con `default_factory=list` fa fallire l'intera richiesta con
  `Invalid schema for response_format 'AgentOutput': 'required' ... Missing 'cited_sources'`.
  Quindi `AgentOutput` non può avere default: `cited_sources` è obbligatorio, con lista vuota
  quando non ci sono fonti. Da ricordare per ogni modello Pydantic passato come `response_format`.

## ADR-027 — Gli artifact dei tool sono leggibili: ADR-002 è realizzabile

- **Contesto**: era il rischio architetturale più grave del progetto. Se il passo di structured
  output avesse nascosto i `ToolMessage`, il livello deterministico di SPEC §5 sarebbe stato
  irrealizzabile e ADR-002 da riprogettare.
- **Esito**: **verificato funzionante**. Lo stato restituito da `create_agent` contiene sia
  `structured_response` (istanza `AgentOutput`) sia `messages`, e il `ToolMessage` del turno
  espone `artifact` intatto:
  `[{'doc_id': 'guides/bulbi_autunnali.md', 'score': 0.91, 'chunk_id': 'c1'}, ...]`.
- **Conseguenze**: `response.py` può intersecare `cited_sources` con i documenti realmente
  restituiti dal retrieval, esattamente come previsto. Nello spike il modello ha citato solo
  `guides/bulbi_autunnali.md` pur avendone ricevuti due, quindi l'intersezione avrà davvero
  lavoro da fare.
- **Osservazione di contorno**: senza la data di business nel system prompt il modello ha
  risposto in modo evasivo ("se siamo già in questo periodo..."). Conferma sul campo la necessità
  di iniettare la data dinamicamente, come prescrive SPEC §8 punto 2.

## ADR-028 — Memoria: `SummarizationMiddleware`, con prompt e rilevamento propri

- **Contesto**: SPEC §9 prescriveva la summarization "verificando nome e parametri sulla versione
  installata". Spike n.3.
- **API reale**: `SummarizationMiddleware(model, *, trigger, keep, token_counter, summary_prompt,
  trim_tokens_to_summarize)`. `trigger` e `keep` sono **tuple**, non interi:
  `trigger=("tokens", 2500)` (oppure `("messages", n)` / `("fraction", f)`) e
  `keep=("messages", 6)`. Il default di `keep` è 20 messaggi.
- **Il prompt predefinito è inadatto**: è scritto per un agente di programmazione, con sezioni
  `SESSION INTENT` / `ARTIFACTS` / `NEXT STEPS`, e butterebbe via proprio ciò che serve al
  customer care. Il prompt personalizzato di SPEC §9 non è un abbellimento, è necessario.
- **Verifica comportamentale**: con `trigger=("messages", 4)` e `keep=("messages", 2)` la
  summarization scatta e il conteggio dei messaggi resta fermo a 4 invece di crescere. Il
  riassunto prodotto dal nostro prompt ha conservato **il numero d'ordine 1042 del turno 1**, il
  vincolo del cliente ("coltiva solo sul balcone, in vaso, poco sole") e la domanda rimasta
  senza risposta. Al turno 4 l'agente ha ancora risposto correttamente "1042".
- **Falso negativo da evitare**: la prima esecuzione usava `trigger=("tokens", 250)` e la
  summarization **non è mai scattata** su una conversazione di quattro turni brevi. Il numero
  d'ordine sopravviveva banalmente, perché non era stato riassunto nulla. Un test di memoria che
  non verifica *anche* che il trigger sia scattato non dimostra niente: in fase 5 il test deve
  asserire entrambe le cose.
- **Dove finisce il riassunto**: viene iniettato come `HumanMessage` in posizione 0, preceduto
  dalla stringa **in inglese** `"Here is a summary of the conversation to date:"`, hardcoded in
  `_build_new_messages` e non configurabile. Lo stato espone solo `messages`, nessun campo
  separato. Per il log di fase 5 e la demo del notebook, il rilevamento è quindi: messaggio 0 di
  tipo `HumanMessage` che inizia con quel marcatore. Da citare come piccolo difetto: testo
  inglese dentro una conversazione interamente italiana.

## ADR-029 — Il provider reale è OpenRouter: ADR-015 va rivisto

- **Contesto**: la chiave fornita in `.env` ha prefisso `sk-or-v1`, cioè è una chiave
  **OpenRouter**, mentre `GREENTHUMB_LLM_MODEL` era `openai/gpt-4.1-mini`. LiteLLM instradava
  quindi direttamente a OpenAI, che rispondeva `401 invalid_api_key`.
- **Verificato funzionante su OpenRouter** (prefisso `openrouter/openai/gpt-4.1-mini`):
  chiamata semplice, tool calling, structured output nativo, agente completo, memoria con
  summarization, e **RAGAS `Faithfulness`** (punteggio 1.0) con un client
  `AsyncOpenAI(base_url="https://openrouter.ai/api/v1")` passato a `llm_factory`.
- **Due vincoli pratici emersi**:
  1. **Tetto di credito.** Senza un `max_tokens` esplicito LiteLLM chiede fino a 65536 token di
     output e OpenRouter risponde `402`: la chiave "can only afford ~24668". Tutte le chiamate
     vanno quindi fatte con `max_tokens` esplicito e contenuto.
  2. **DeepEval** inizialmente non passava, non per incompatibilità di API ma per lo stesso
     `402`. **Risolto** con l'acquisto di credito (ADR-032) e il tetto di ADR-031.
     **Punto chiuso**: OpenRouter restituisce i logprob richiesti da `GEval` — verificato con
     una chiamata diretta, `top_logprobs=20` richiesti e 20 ricevuti — e `GEval` funziona
     end-to-end (punteggio 1.0 con motivazione in italiano). SPEC §10.3 resta invariata.
- **Osservazione sulla riproducibilità**: OpenRouter bilancia le richieste fra più fornitori
  a monte (nell'errore diagnostico compaiono sia Azure sia OpenAI). Due esecuzioni identiche
  possono essere servite da infrastrutture diverse — da citare fra i limiti nella relazione.
- **Stato**: **decisione sospesa**, in attesa dell'utente. ADR-015 va emendato di conseguenza.

## ADR-030 — Pinning del fornitore OpenRouter: non implementabile via LiteLLM

- **Contesto**: si era deciso di vincolare OpenRouter a un solo fornitore a monte, per rendere
  riproducibile il confronto prima/dopo della fase 7 (OpenRouter smista fra Azure, OpenAI e altri).
- **Verifica**: OpenRouter accetta il pinning solo nel **corpo** della richiesta, col campo
  `provider: {"order": [...], "allow_fallbacks": false}`. In litellm 1.102.0 la classe
  `OpenrouterConfig.map_openai_params` costruisce un `extra_body` **nuovo** a partire dai soli
  `transforms`, `models` e `route`, e poi lo **assegna**, scartando qualunque `extra_body`
  passato dal chiamante. Misurato direttamente: passando
  `extra_body={"provider": {"order": ["OpenAI"], "allow_fallbacks": False}}` il risultato mappato
  è `{}`. Inoltre `get_supported_openai_params` per openrouter espone solo `extra_headers`, e il
  routing di OpenRouter non è controllabile via header.
- **Decisione**: non si implementa in codice. Il pinning va impostato, se lo si vuole, dalle
  **preferenze di account su OpenRouter** (lista di fornitori consentiti/esclusi), che agiscono
  su tutte le richieste della chiave senza toccare il nostro codice.
- **Alternative scartate**: patchare `OpenrouterConfig` (monkey-patch di una classe interna di
  litellm: fragile e indifendibile in un progetto d'esame); abbandonare LiteLLM (è un requisito
  d'esame, R1).
- **Conseguenze**: se l'impostazione di account non viene applicata, la variabilità fra fornitori
  resta e va citata fra i limiti nella relazione. Da rivalutare se litellm aggiungerà il supporto.

## ADR-031 — `max_tokens` esplicito su ogni chiamata

- **Contesto**: senza un tetto esplicito LiteLLM richiede fino a 65536 token di output, e
  OpenRouter rifiuta con `402` quando il credito residuo non li copre (ADR-029). Non è solo un
  problema di budget: un tetto alto lascia anche che una risposta degeneri.
- **Decisione**: nuova variabile `GREENTHUMB_MAX_OUTPUT_TOKENS` (default 1024), applicata a ogni
  costruzione del modello. Le risposte di customer care sono brevi per natura; 1024 token sono
  già generosi.
- **Conseguenze**: rende il costo per chiamata prevedibile e limita l'esposizione al `402`.
  Va aggiunta a SPEC §12 e a `.env.example`.

## ADR-032 — Modelli a pagamento invece dei modelli gratuiti

- **Contesto**: l'intero progetto potrebbe girare a costo zero. Il costo misurato è però
  minimo: gli spike della fase 0 (circa trenta chiamate fra agente, tool calling, structured
  output, memoria e RAGAS) sono costati **$0.0042**. Una esecuzione completa dell'evaluation
  (20 conversazioni più i giudici, che fanno più chiamate interne per metrica) si stima sulle
  200–300 chiamate, dell'ordine di **$1**; la fase 7 ne prevede due.
- **Verifica della via gratuita**: interrogando il catalogo OpenRouter, dei 21 modelli `:free`
  **6 supportano sia `tools` sia `structured_outputs`** (`qwen/qwen3.8-27b:free`,
  `nvidia/nemotron-3-super-120b-a12b:free`, `nex-agi/nex-n2.5-pro:free` e altri), e due
  espongono anche i `logprobs`. L'architettura di ADR-026/027 sopravvivrebbe: il problema non
  è tecnico.
- **Decisione**: acquistare credito (~$5) e usare modelli a pagamento.
- **Alternative scartate**, con la ragione per ciascuna:
  - *modelli `:free` su OpenRouter*: il limite verificato sull'account è **50 richieste al
    giorno**, cioè 5–6 giorni di quota per ogni singola esecuzione dell'evaluation. Soprattutto,
    i modelli `:free` vengono ruotati e ritirati con frequenza: il notebook consegnato, che deve
    girare con "Esegui tutto" su un runtime pulito anche settimane dopo, potrebbe fallire davanti
    a chi valuta. È un rischio sul deliverable, non sullo sviluppo.
  - *piano gratuito di Google AI Studio*: limiti giornalieri plausibilmente molto più alti e
    buon italiano, ma imporrebbe di ricablare RAGAS e DeepEval, perdendo il percorso nativo
    verificato in ADR-024.
  - *modello locale via Ollama*: gratuito e senza quote, ma non disponibile su Colab, che è
    l'ambiente di consegna.
- **Conseguenze**: la via gratuita non fa risparmiare cinque dollari, fa spendere giorni di
  attesa e aggiunge un rischio sulla riproducibilità del deliverable. Il confronto è documentato
  qui perché è una scelta ingegneristica motivata, non una resa al costo.

## ADR-033 — Due forme dello stesso identificatore di modello

- **Contesto**: il progetto usa lo stesso modello per strade diverse, e le due strade vogliono
  identificatori diversi. Scoperto facendo funzionare i giudici per davvero.
- **Le due forme**:
  - **LiteLLM** (agente): richiede il prefisso di rotta — `openrouter/openai/gpt-4.1-mini`.
  - **RAGAS e DeepEval**: scavalcano LiteLLM e parlano direttamente all'endpoint
    OpenAI-compatibile di OpenRouter (`https://openrouter.ai/api/v1`), dove `openrouter/...`
    non è un modello esistente e la chiamata fallisce. Vogliono lo slug del provider:
    `openai/gpt-4.1`.
- **Decisione**: una sola proprietà, `Settings.judge_model_slug`, che rimuove il prefisso di
  rotta. Nessun modulo ricava l'identificatore da sé.
- **Alternative scartate**: due variabili d'ambiente distinte (si disallineano al primo cambio di
  modello); `.removeprefix()` sparso nei moduli dell'evaluation (la duplicazione che ADR-006 ha
  già eliminato per i `doc_id`).
- **Conseguenze**: verificato end-to-end con `scripts/spikes/spike_judges.py`, che esegue
  davvero le quattro metriche previste da SPEC §10.3: Faithfulness 1.0,
  ContextPrecisionWithReference ~1.0, GEval 1.0, AnswerRelevancy 0.5.
- **Osservazione per la fase 7**: **AnswerRelevancy ha dato 0.5 su una risposta corretta e
  pertinente**. Probabile causa: la metrica penalizza le affermazioni accessorie ("in terreno
  ben drenato") come non richieste dalla domanda. Non è un difetto del sistema ma della
  calibrazione della metrica su risposte brevi in italiano: va tenuto d'occhio in fase 7, dove
  un punteggio basso va attribuito alla causa giusta prima di "correggere" l'agente.

## ADR-034 — `short_description` e `season` nel catalogo

- **Contesto**: SPEC §4.2 prevedeva sei campi per prodotto. Scrivendo 16 schede prodotto a mano,
  nulla avrebbe impedito che una scheda descrivesse il prodotto in modo diverso dal catalogo, o
  che indicasse un periodo di semina incoerente con le guide stagionali.
- **Decisione**: due campi in più.
  - `short_description`: una riga rivolta al cliente, in italiano. La scheda prodotto la espande
    e **non può contraddirla**; `validate_data.py` non può verificarlo semanticamente, ma il
    campo rende la contraddizione evidente a chi scrive e a chi rivede.
  - `season`: le stagioni in cui il prodotto è rilevante, con valori **identici** a quelli
    restituiti da `clock.season_of()` (`primavera`, `estate`, `autunno`, `inverno`). Tutte e
    quattro significa «tutto l'anno».
- **Perché `season` conta più di quanto sembri**: il system prompt inietta la data di business
  e la stagione corrente (SPEC §8). Con `season` nel catalogo, la stagionalità diventa un dato
  **confrontabile dal codice** invece che una deduzione dell'LLM dal testo libero delle schede.
  Alla business date del 12 ottobre risultano rilevanti 10 prodotti su 16, quindi le domande
  stagionali dell'evaluation hanno materiale concreto su cui discriminare.
- **Alternative scartate**: restare ai sei campi (allineamento affidato alla sola diligenza di
  chi scrive 35 documenti); ricavare la stagione dal testo delle schede con un parsing (fragile,
  e contrario ad ADR-002: se un dato può essere strutturato, va strutturato).
- **Conseguenze**: `validate_data.py` verificherà che ogni `season` sia non vuota e contenga solo
  valori ammessi, importandoli da `clock` invece di duplicarli. SPEC §4.2 aggiornata.

## ADR-035 — 14 guide invece di 12, knowledge base a 37 documenti

- **Contesto**: SPEC §4.3 pianificava 12 guide, per un totale di 35 documenti. La stesura ne ha
  prodotte 14: lo scostamento è nato distribuendo i temi, non da una scelta deliberata, ed è
  stato segnalato prima di consolidarlo.
- **Decisione**: tenere tutte e 14 e allineare la specifica. Le due eccedenti —
  `raccolta_conservazione_semi.md` e `riconoscere_terriccio_adatto.md` — non duplicano altri
  documenti: la prima copre germinabilità e conservazione delle sementi, tema che nessuna scheda
  prodotto affronta in modo trasversale; la seconda copre pH, struttura e scelta del substrato,
  che le due schede dei terricci trattano solo dal proprio punto di vista.
- **Alternative scartate**: eliminarne due per aderenza al conteggio pianificato. Il conteggio è
  un mezzo, non un requisito: R5 chiede almeno 30 documenti, e la copertura più ampia migliora
  il retrieval senza introdurre ridondanza.
- **Conseguenze**: KB a 37 documenti (16 schede, 14 guide, 7 policy). SPEC §1 e §4.3 aggiornate.
  22 documenti risultano rilevanti alla business date del 12 ottobre, quindi le domande
  stagionali dell'evaluation hanno materiale sufficiente per discriminare.
- **Nota di metodo**: la deviazione è stata dichiarata invece che assorbita in silenzio. Per un
  progetto valutato anche sulla tracciabilità delle scelte, uno scostamento documentato vale più
  di un conteggio rispettato.

## ADR-036 — Ordini generati da codice, non scritti a mano

- **Contesto**: servono almeno 24 ordini coerenti col catalogo, con sette stati coperti e
  alcuni casi limite precisi. `data/orders.json` è un deliverable ed è versionato.
- **Decisione**: generazione da `scripts/generate_orders.py` con **seed fisso** (20261012) e date
  espresse come offset dalla business date, mai da `datetime.now()`. Gli ordini "speciali" non
  sono casuali: `ORDER_PLAN` fissa stato, offset e SKU obbligatori di ciascuno, e l'ordine 1042
  è scritto a mano perché SPEC §4.4 ne fissa cliente, date, tracking e totale.
- **Alternative scartate**: scrivere i 26 ordini a mano (26 totali da ricalcolare a ogni
  variazione di prezzo); generazione interamente casuale (nessuna garanzia sui casi limite).
- **Conseguenze**: due esecuzioni producono un file identico byte per byte, verificato da test.
  Cambiare un prezzo nel catalogo e rieseguire `make data` riallinea tutti gli ordini.

## ADR-037 — Il validatore viene testato sui dati rotti, non su quelli giusti

- **Contesto**: `scripts/validate_data.py` automatizza i controlli fatti a mano mentre i dati
  venivano scritti. Un validatore che passa sempre è indistinguibile dall'assenza di validatore.
- **Decisione**: i test corrompono i dati di proposito — SKU malformato, `perishable` incoerente
  con la categoria, stagione inesistente, `kb_path` senza estensione, scheda prodotto mancante,
  totale sbagliato, prezzo divergente dal catalogo, ordine 1042 assente o con data errata,
  copertura di uno stato scesa sotto due — e verificano che ciascuna venga **segnalata**.
- **Conseguenze**: 52 test verdi. Il valore si è visto subito: il test sui casi limite ha
  scoperto che l'ordine 1054, pensato come reso deperibile **fuori termine**, veniva generato
  con la richiesta entro 10 giorni dalla consegna, cioè dentro i 14 giorni di policy. Il caso
  limite non esisteva. Corretto il generatore, non il test.
- **Nota tecnica**: i controlli sul testo dei documenti normalizzano gli spazi prima di cercare
  un valore, perché le righe sono mandate a capo a 100 colonne e una cifra può trovarsi spezzata
  fra due righe — errore in cui era incorsa una verifica manuale precedente.

## ADR-038 — Una sola versione di ruff, non due

- **Contesto**: un commit è stato rifiutato dal hook pre-commit per una regola (`UP038`) che
  `make lint`, eseguito un istante prima, dichiarava soddisfatta.
- **Causa**: pre-commit non usa il ruff del progetto. Crea un proprio ambiente isolato alla
  versione indicata in `.pre-commit-config.yaml`, che era `v0.9.6`, mentre `uv sync` aveva
  installato `ruff 0.16.8`. Due linter diversi sullo stesso codice, con due verdetti diversi.
- **Decisione**: allineare `rev` alla versione presente nel gruppo `dev` di `pyproject.toml`, con
  un commento che spiega perché i due numeri devono restare uguali.
- **Conseguenze**: `make lint` e il hook ora concordano. È un allineamento da rifare a ogni
  aggiornamento di ruff — il commento serve proprio a ricordarlo. Da citare nella relazione fra
  gli attriti pratici del tooling: un controllo di qualità che si contraddice da solo erode la
  fiducia nel controllo stesso.

## ADR-039 — Metadati appiattiti al caricamento, non all'indicizzazione

- **Contesto**: `season` e `related_skus` sono liste nel frontmatter, ma Chroma accetta solo
  valori scalari come metadati (str, int, float, bool). Passargli una lista solleva un errore
  al momento dell'indicizzazione, cioè lontano dalla causa.
- **Decisione**: appiattirle in `kb_loader.py`, unendole con la virgola, così che un
  `KbDocument` sia **già** pronto per il vector store. Il caricatore garantisce l'invariante,
  invece di lasciarla al chiamante.
- **Alternative scartate**: convertire in `build_index` (la stessa conversione andrebbe ripetuta
  in ogni altro consumatore); serializzare in JSON (illeggibile in un filtro Chroma).
- **Conseguenze**: i metadati dei chunk sono tutti stringhe, verificato da test. Un filtro per
  stagione dovrà usare una sottostringa, non un confronto esatto.

## ADR-040 — Soglie di retrieval calibrate: 0.813 e 0.864

- **Contesto**: gli score di e5 si concentrano in una fascia alta e stretta e vanno quindi
  calibrati empiricamente, non indovinati. Misurato con `scripts/probe_retrieval.py` su 12 query
  pertinenti e 8 fuori tema, tutte formulate **senza riusare le frasi dei documenti** — usare le
  parole del documento gonfierebbe gli score e calibrerebbe su una situazione irreale.
- **Risultati**: **hit@1 = 12/12, hit@4 = 12/12**, contro un obiettivo di fase 2 di hit@4 ≥ 90%.

  | Gruppo | min | media | mediana | max |
  |---|---|---|---|---|
  | Pertinenti | 0.8195 | 0.8626 | 0.8638 | 0.8873 |
  | Fuori tema | 0.7346 | 0.7844 | 0.7967 | 0.8063 |

- **Decisione**: `LOW = 0.813` (punto medio fra i due gruppi, massimo margine per lato) e
  `HIGH = 0.864` (mediana dei pertinenti: circa metà dei recuperi validi può dichiarare
  confidence alta). Promosse a **default in `config.py`**, così il sistema funziona senza
  che nessuno debba tarare il `.env`.
- **L'avvertimento è confermato, e in forma severa**: la separazione è di appena
  **+0.0132** (peggior pertinente 0.8195, miglior fuori tema 0.8063). Con soglia a 0.813 restano
  circa 0.0065 di margine per lato, stimati su sole 20 query.
- **Conseguenza architetturale**: la soglia **non è un confine affidabile** e non va trattata
  come tale. È uno dei tre presidi contro le risposte fuori ambito, insieme al rifiuto esplicito
  istruito nel system prompt (SPEC §8) e al cap sulla `confidence`, che rende comunque
  dichiaratamente incerta una risposta basata su un recupero borderline. La fase 7 rivaluta le
  soglie su 20 conversazioni indipendenti da queste query.
- **Nota sul comportamento del retrieval**: il motore restituisce **sempre** qualcosa. Alla
  domanda «qual è la capitale del Giappone?» risponde con la guida alla concimazione, a 0.7433.
  È la soglia, non il motore, a dover dichiarare che nessun documento è pertinente.
- Tabelle complete in `docs/RETRIEVAL_CALIBRATION.md`.

## ADR-041 — Prefissi e5: l'avvertimento era sovrastimato, si mantengono comunque

- **Contesto**: ADR-022 aveva misurato i prefissi `query: `/`passage: ` su 4 documenti
  giocattolo, trovando un effetto marginale, e si era impegnato a **rimisurarli** sulla
  knowledge base reale, dove i distrattori sono altri testi di giardinaggio anziché domande
  sulla capitale del Giappone. Impegno mantenuto.
- **Misura** (37 documenti, 207 chunk, stesse 20 query della calibrazione):

  | | hit@1 | hit@4 | Peggior pertinente | Miglior fuori tema | Separazione |
  |---|---|---|---|---|---|
  | **Con** prefissi | **12/12** | 12/12 | 0.8195 | 0.8063 | **+0.0132** |
  | **Senza** prefissi | 11/12 | 12/12 | 0.8268 | 0.8139 | +0.0130 |

- **Esito**: i prefissi recuperano una query in prima posizione e lasciano la separazione
  praticamente identica. **Il «crollo silenzioso» descritto dalla documentazione non si
  verifica** su
  questo corpus, né sul campione giocattolo della fase 0.
- **Decisione**: mantenerli. Sono l'uso documentato del modello, non costano nulla e il
  miglioramento su hit@1 è reale, per quanto piccolo. Sono applicati dentro `E5Embeddings`, così
  nessun chiamante può dimenticarli.
- **Conseguenze**: l'avvertimento resta utile come promemoria ma va ridimensionato nella
  relazione, con i numeri. Vale la lezione generale: un'insidia nota va misurata sul proprio
  corpus prima di essere trattata come critica.

## ADR-042 — Chunking guidato dagli heading, non dalla dimensione

- **Contesto**: SPEC §6 prescriveva `MarkdownHeaderTextSplitter` con ricaduta su
  `RecursiveCharacterTextSplitter` oltre ~1200 caratteri.
- **Esito misurato**: 37 documenti producono **207 chunk**, circa 5,6 per documento, e su un
  documento di esempio a tre heading la suddivisione produce esattamente tre chunk, uno per
  sezione, senza ricadute sul taglio a caratteri.
- **Prefisso di contesto**: ogni chunk è preceduto da titolo del documento e percorso degli
  heading (`Guida di esempio — Titolo principale > Dosaggi`). Senza, un chunk che riporta
  «Dose: 30 g/m²» non dice di quale prodotto parli, e con quattro fertilizzanti a catalogo
  l'ambiguità sarebbe concreta.
- **Id deterministici**: `chunk_id = "<doc_id>#<indice>"`, usati come id in Chroma. Una
  ricostruzione dell'indice **sovrascrive** invece di duplicare, il che rende `make index`
  idempotente.
- **Conseguenze**: coperto da test che non caricano il modello di embedding — il chunking è
  logica pura e va testato come tale, senza scaricare 1,1 GB in CI.

## ADR-043 — Una soglia di rilevanza a zero deve fallire, non passare in silenzio

- **Contesto**: il tool RAG, appena scritto, ha riportato `threshold: 0.0` invece del valore
  calibrato 0.813. Causa: il `.env` era stato copiato dal `.env.example` **prima** della fase 2
  e conteneva ancora i segnaposto `GREENTHUMB_RETRIEVAL_SCORE_LOW=0.0`, che sovrascrivevano il
  default calibrato promosso in `config.py`.
- **Perché è grave**: il retrieval restituisce **sempre** i suoi top-k (ADR-040). Con soglia a
  zero ogni risultato conta come rilevante, quindi «qual è la capitale del Giappone?» avrebbe
  prodotto documenti "pertinenti", `sources` popolate con riferimenti irrilevanti e nessun cap
  `low` sulla confidence. Il filtro era disattivato **senza alcun sintomo visibile**: il sistema
  continuava a rispondere, semplicemente peggio.
- **Decisione**: un validatore rifiuta `retrieval_score_low <= 0` con un messaggio che nomina il
  valore calibrato, il documento che lo giustifica e le due azioni possibili (rimuovere la riga
  dal `.env`, oppure impostarla al valore corretto). Valori diversi da zero restano liberi: si
  vieta la disattivazione, non la taratura.
- **Dettaglio implementativo non ovvio**: il vincolo `gt=0.0` sul `Field` era la prima stesura,
  ma i vincoli di campo scattano **prima** dei validatori e sostituivano il messaggio utile con
  un generico «Input should be greater than 0». Il vincolo è stato rimosso, con un commento che
  spiega perché non va rimesso.
- **Conseguenze**: coperto da test di regressione. Lezione generale: un valore di configurazione
  che disattiva un presidio di sicurezza non deve essere un valore ammissibile.

## ADR-044 — L'isolamento dei test vale per la sessione, non per il singolo test

- **Contesto**: terza manifestazione dello stesso problema. ADR-025 aveva chiuso la via
  dell'ambiente (`load_dotenv()` di DeepEval), ma `Settings` legge `.env` **da sé**: il `.env`
  con la soglia a zero faceva fallire test che con le soglie non c'entravano nulla. Peggio, la
  prima correzione — una fixture `autouse` di funzione — non bastava, perché **le fixture di
  modulo girano prima di quelle di funzione**, e qualunque fixture che legga la configurazione a
  livello di modulo arrivava prima dell'isolamento.
- **Decisione**: una fixture `autouse` di **sessione** che stacca `Settings` dal file una volta
  sola, prima di qualunque altra cosa, affiancata da quella di funzione che mantiene pulito
  l'ambiente fra un test e l'altro.
- **Conseguenze**: 133 test verdi, e verificato che reggono anche con il plugin DeepEval
  **riattivato a forza**. I test unitari non dipendono più in alcun modo dalla configurazione
  locale di chi li esegue: la CI, il portatile dello sviluppatore e Colab danno lo stesso esito.
- **Lezione da citare nella relazione**: l'accoppiamento fra test e configurazione locale si
  ripresenta da direzioni diverse — variabile d'ambiente, file letto direttamente, ordine di
  esecuzione delle fixture. Va chiuso in modo esplicito e verificato, non dato per risolto dopo
  il primo intervento.

## ADR-045 — Chunking ripulito dalla ripetizione del titolo, e seconda calibrazione

- **Contesto**: scrivendo il tool RAG si è visto cosa il modello legge davvero. Ogni chunk
  conteneva il titolo del documento **fino a tre volte**: come prefisso di contesto, come
  percorso di heading, e come riga Markdown letterale (`# Titolo`), perché il chunking usava
  `strip_headers=False`.
- **Correzione**: `strip_headers=True`, così la riga letterale sparisce (il testo dell'heading
  raggiunge comunque il chunk tramite il prefisso), e un percorso di heading che **ripete il
  titolo** viene omesso. Verificato prima di decidere: l'`h1` coincide col titolo, o ne è un
  prefisso, in 13 documenti su 37; negli altri 24 porta significato proprio
  («Il balcone ha tre vincoli», «Ingiallimento: leggere il sintomo») e va conservato. Scartata
  quindi l'ipotesi più semplice di eliminare sempre il livello `h1`.
- **Esito misurato**: 206 chunk invece di 207, 519 caratteri medi invece di 546.

  | Chunking | hit@1 | hit@4 | Separazione |
  |---|---|---|---|
  | Ridondante | 12/12 | 12/12 | +0.0132 |
  | Pulito | 11/12 | 12/12 | +0.0103 |

- **Onestà del risultato: il chunking pulito NON migliora il retrieval.** `hit@1` perde una
  query e la separazione si restringe di 0.0029. La query persa è però un pareggio a
  **0.0004** fra tre chunk che rispondono tutti alla domanda, con il documento atteso secondo.
  Non si è allargato a posteriori l'insieme dei documenti accettabili per far tornare la
  metrica: sarebbe il modo più rapido di rendere inutile un benchmark.
- **Decisione**: tenere il chunking pulito. Il guadagno non è nelle metriche ma in ciò che il
  modello legge a ogni turno: 5% di caratteri in meno e nessuna ripetizione priva di
  informazione. La differenza sulle metriche rientra nel rumore di un campione di 20 query.
- **Conseguenze**: indice ricostruito, soglie ricalibrate (`LOW` resta 0.813, `HIGH` scende da
  0.864 a 0.863), `docs/RETRIEVAL_CALIBRATION.md` riscritto per intero. ADR-040 e ADR-041 vanno
  letti alla luce di questa seconda misura.

## ADR-046 — L'ablazione sui prefissi diventa uno script versionato, e il verdetto si complica

- **Contesto**: la misura sui prefissi e5 era stata fatta due volte con file usa-e-getta, ed è
  citata in DECISIONS.md. Una misura citata in una relazione deve essere riproducibile.
- **Decisione**: `scripts/ablation_e5_prefixes.py`, versionato, che costruisce un secondo indice
  temporaneo senza prefissi e lo confronta con quello di produzione sulle stesse query.
- **Risultati sulle quattro combinazioni**:

  | Chunking | Prefissi | hit@1 | hit@4 | Separazione min/max | Distanza fra le medie |
  |---|---|---|---|---|---|
  | Ridondante | con | 12/12 | 12/12 | +0.0132 | 0.0782 |
  | Ridondante | senza | 11/12 | 12/12 | +0.0130 | 0.0704 |
  | **Pulito** | **con** | 11/12 | 12/12 | +0.0103 | **0.0779** |
  | Pulito | senza | 11/12 | 12/12 | **+0.0181** | 0.0701 |

- **Le due statistiche si contraddicono**: sulla separazione fra gli estremi i prefissi
  peggiorano le cose (+0.0103 contro +0.0181); sulla distanza fra le medie le migliorano
  (0.0779 contro 0.0701), e con un margine più ampio.
- **Lettura**: min e max, su 12 e 8 query, sono determinati da **singole osservazioni** e sono la
  statistica meno stabile disponibile. La distanza fra le medie usa tutti i dati ed è coerente
  in entrambe le configurazioni di chunking. È un promemoria utile per la fase 7: la metrica con
  cui si misura un intervento va scelta **prima** di vedere i risultati, altrimenti si finisce a
  scegliere quella che dice ciò che si sperava.
- **Decisione**: mantenere i prefissi. Sono l'uso documentato del modello, la statistica più
  stabile li favorisce, `hit@1` e `hit@4` sono identici nelle due varianti, e la soglia operativa
  resta comunque presidiata da altri due meccanismi (ADR-040).
- **Conseguenza per la relazione**: l'avvertimento della documentazione di e5 — «senza i
  prefissi la qualità del retrieval crolla in modo silenzioso» — **non è confermato da nessuna
  delle quattro misure**. Va riportato come esempio concreto di insidia ereditata dalla
  documentazione e smentita dalla misura sul proprio corpus.

## ADR-047 — `RunnableConfig` va dichiarato senza default, altrimenti non viene iniettato

- **Contesto**: il tool di escalation ha bisogno del `session_id` per l'idempotenza e per
  `needs_human`, ma il modello **non deve poterlo scegliere, inventare od omettere**.
  L'identificatore arriva quindi dal `RunnableConfig` (`configurable.thread_id`, che l'agente
  imposta uguale al `session_id`), non dagli argomenti del tool.
- **Trappola trovata alla prima esecuzione**: con la firma `config: RunnableConfig | None = None`
  — che sembra la scrittura prudente — l'iniezione **non avviene**, e la funzione riceve `None`.
  Nessun errore, nessun avviso: il `session_id` cadeva sul valore di ripiego e tutte le
  conversazioni finivano in un'unica sessione condivisa, distruggendo sia l'idempotenza dei
  ticket sia il flag `needs_human`.
- **Misurato sulle quattro combinazioni**:

  | Firma del parametro | Iniettato | Esposto nello schema |
  |---|---|---|
  | `config: RunnableConfig` (nessun default) | **sì** | no |
  | `config: RunnableConfig \| None = None`, schema esplicito | no | no |
  | `config: RunnableConfig` (nessun default), schema inferito | **sì** | no |
  | `config: RunnableConfig \| None = None`, schema inferito | no | **sì, visibile al modello** |

- **Decisione**: parametro annotato `RunnableConfig` **senza default**, con un commento nel
  docstring che spiega perché non va aggiunto. L'ultima riga della tabella è il caso peggiore:
  il default non solo disattiva l'iniezione, ma con schema inferito espone `config` fra gli
  argomenti che il modello può riempire.
- **Conseguenze**: coperto da due test, uno sull'isolamento fra sessioni e uno che verifica che
  lo schema mostrato al modello contenga esattamente `reason`, `summary`, `order_id`. Da citare
  nella relazione: è un caso da manuale di fallimento silenzioso in cui la scrittura difensiva
  è quella sbagliata.

## ADR-048 — Registro delle escalation separato dal tool, e duplicazione sorvegliata dei tempi

- **Contesto**: `escalations.jsonl` non è un semplice log. `needs_human` è derivato da lì
  (ADR-008), quindi il file è la risposta autorevole alla domanda «questa conversazione richiede
  un operatore?».
- **Decisione**: `escalations_repository.py`, speculare a `orders_repository.py` — il modulo
  possiede il file, il tool resta sottile. Aggiunge un modulo rispetto all'elenco di SPEC §3, in
  coerenza con «I/O ai bordi, logica pura al centro».
- **Idempotenza per sessione *e* motivo**: un cliente che ripete un reclamo non genera un
  secondo ticket, ma lo stesso cliente che segnala merce danneggiata **e** chiede un operatore ne
  genera legittimamente due. Una riga malformata viene saltata invece di sollevare: un log
  corrotto non deve impedire di rispondere a un cliente.
- **Duplicazione deliberata e sorvegliata**: i tempi di presa in carico (4 ore lavorative per
  `damaged_or_wrong_item` e `safety`, 1 giorno lavorativo per gli altri cinque) sono ripetuti nel
  tool, perché un cliente a cui si comunica il numero di ticket deve sapere **nello stesso
  respiro** quando sarà ricontattato, senza un secondo giro di retrieval. La duplicazione invita
  alla divergenza, quindi un test verifica che quelle stesse formule compaiano ancora in
  `policies/contatti_orari.md`, con un messaggio d'errore che spiega cosa è andato fuori
  sincrono.
- **Conseguenze**: è l'eccezione motivata alla regola seguita nel tool ordini, dove invece la
  soglia dei 14 giorni **non** viene enunciata. Il criterio che distingue i due casi: qui il dato
  serve a completare un'azione già decisa, là servirebbe a decidere, e una decisione va presa
  sulla fonte, non su una copia.

## ADR-049 — Un fake chat model non puo' pilotare questo agente

- **Contesto**: il PLAN prevedeva «test unitari del wiring con fake chat model». Provato per
  davvero, il fake non regge il ciclo.
- **Due ostacoli indipendenti**:
  1. `GenericFakeChatModel.bind_tools` **solleva `NotImplementedError`**: è un metodo astratto
     della classe base, non implementato da nessuno dei sei fake di `langchain_core`. Un agente
     con tool non è quindi costruibile sopra un fake senza sottoclassarlo.
  2. Anche sottoclassandolo per accettare il binding, il ciclo non termina: `create_agent`
     ottiene l'output strutturato dal **`response_format` nativo del provider** (ADR-026), un
     protocollo specifico dell'implementazione che il fake non emula. L'agente continua a
     chiamare il modello fino al limite di iterazioni, esaurendo le risposte preparate.
- **Decisione**: i test unitari verificano **cosa è stato cablato**, non il comportamento del
  ciclo: modello con temperatura e tetto di token corretti, tre tool nell'ordine atteso, tutti
  con `content_and_artifact`, soglia di retrieval effettivamente propagata, checkpointer
  attaccato, canale `structured_response` esposto, fallback conforme allo schema. Il
  comportamento del ciclo è coperto dai test marcati `llm`.
- **Conseguenza per la fase 6**: `response.py` va testato con **trace costruite a mano**, non
  eseguendo l'agente. Il PLAN lo prevedeva già («trace costruite a mano, nessun LLM»): la
  scoperta conferma quella scelta invece di contraddirla.
- **Nota secondaria**: `create_agent` rifiuta due istanze della **stessa classe** di middleware
  con `AssertionError: Please remove duplicate middleware instances`. Vincolo da ricordare in
  fase 5, quando si aggiunge la summarization: deve essere di tipo diverso da quelli già cablati,
  cosa che è.

## ADR-050 — Il limite di iterazioni termina la corsa, non solleva

- **Contesto**: SPEC §8 chiede un limite al ciclo ReAct «con risposta di fallback», non un
  errore verso il cliente.
- **Decisione**: `ModelCallLimitMiddleware(run_limit=8, exit_behavior="end")`. Fra le due
  modalità disponibili, `"error"` solleverebbe un'eccezione a metà conversazione; `"end"` salta
  alla fine del grafo e lascia che sia `fallback_output()` a fornire la risposta: scuse, rinvio
  a un operatore, indirizzo di contatto, `proposed_confidence="low"`, nessuna fonte citata.
- **Perché 8 resta il numero giusto**: ADR-026 ha stabilito che lo structured output è nativo e
  **non consuma un'iterazione**, quindi il budget è interamente disponibile per il ragionamento
  e le chiamate ai tool. Un turno multi-tool legittimo ne usa tre o quattro.
- **Temperature a 0.0, non genericamente «bassa»**: l'evaluation della fase 7 confronta due
  esecuzioni prima e dopo un intervento correttivo. Con temperatura maggiore di zero, il rumore
  di campionamento comparirebbe come differenza di punteggio che nessuna nostra modifica ha
  causato. Resta comunque la variabilità fra fornitori di OpenRouter (ADR-030).

## ADR-051 — Il system prompt viene ricostruito a ogni chiamata al modello

- **Contesto**: `create_agent(system_prompt=...)` accetta una stringa fissa, congelata alla
  costruzione dell'agente. La data di business e la stagione fanno parte del prompt.
- **Decisione**: middleware `dynamic_prompt`, che invoca `build_system_prompt(clock.today())`
  a ogni chiamata al modello. Il clock è iniettato, quindi con `SystemClock` la data segue il
  tempo reale e con `FrozenClock` resta quella simulata, senza che l'agente debba saperlo.
- **Alternative scartate**: prompt fisso con la data del momento della costruzione (un processo
  di lunga durata, o l'API avviata prima di mezzanotte, direbbe al cliente una data sbagliata);
  iniettare la data nel messaggio utente (la inquina e la rende visibile nella trascrizione).
- **Conseguenze**: il prompt resta una funzione pura testabile senza agente, e il costo è un
  `format()` per chiamata.

## ADR-052 — Struttura del system prompt e criteri di escalation generati dall'enum

- **Contesto**: il system prompt è l'unico punto in cui si governa il comportamento
  dell'agente. Le sette sezioni di SPEC §8 dicono *cosa* deve contenere, non come organizzarlo.
- **Struttura scelta**, in quest'ordine: ruolo e tono → data di oggi → provenienza delle
  informazioni → come affrontare una richiesta → quando chiedere invece di agire → quando
  passare a un operatore → come scrivere la risposta → campi strutturati. L'ordine non è
  casuale: le regole di grounding vengono **prima** delle istruzioni operative, perché sono
  quelle che non ammettono eccezioni, e i campi strutturati per ultimi perché riguardano la
  forma, non la sostanza.
- **I criteri di escalation non sono scritti a mano nel prompt.** Sono generati da
  `ESCALATION_CRITERIA`, un dizionario le cui chiavi sono i valori del `Literal`
  `EscalationReason` che il tool accetta. Un test asserisce che i due insiemi coincidano:
  `set(ESCALATION_CRITERIA) == set(typing.get_args(EscalationReason))`.
- **Perché conta**: un criterio presente nell'enum ma assente dal prompt sarebbe
  **irraggiungibile** — il modello non saprebbe di poterlo usare — e nessun test di
  integrazione lo scoprirebbe se non per caso, perché testerebbe solo i criteri che conosce.
  È la stessa logica di ADR-006 sui `doc_id`: una sola fonte, mai due copie da allineare a mano.
- **Due regole scritte per esteso**, perché non deducibili dai nomi dell'enum e derivanti da
  decisioni prese in ADR: una domanda fuori ambito è un rifiuto cortese e **non** un ticket
  (SPEC §8); un ordine non trovato al primo tentativo chiede conferma e **non** escala
  (ADR-011).
- **Vincolo di dimensione**: un test impone 400–1000 parole. Ogni turno paga il prompt in
  token, e un'istruzione che il modello non legge è peggio di un'istruzione assente. La
  versione attuale è di 722 parole.
- **Istruzioni sui campi strutturati**: il prompt specifica che `cited_sources` deve riportare
  i `doc_id` «nella forma esatta in cui compaiono fra parentesi quadre». Senza questa
  precisazione, il modello scriverebbe riferimenti in forma libera, l'intersezione di ADR-002
  restituirebbe sempre l'insieme vuoto, e `sources` cadrebbe silenziosamente sul fallback.

## ADR-053 — Prime osservazioni dall'agente reale, da portare in fase 7

- **Contesto**: i dieci test di integrazione della fase 4 sono le prime esecuzioni con un
  modello vero. Due osservazioni meritano di essere registrate ora, prima che vengano
  dimenticate.
- **Le chiamate ai tool avvengono in parallelo.** Sull'esempio della traccia il modello emette
  `get_order_status` e `search_knowledge_base` in **un solo** `AIMessage`, quindi il turno
  costa 2 chiamate al modello invece di 3:

  ```
  [1] AIMessage -> ['get_order_status', 'search_knowledge_base']
  [2] ToolMessage (get_order_status)
  [3] ToolMessage (search_knowledge_base)
  [4] AIMessage
  ```

  Conferma con ancora più margine che il limite di 8 (ADR-012, ADR-050) è abbondante.
  Conseguenza per la metrica `tool_selection_accuracy` della fase 7: i tool vanno raccolti da
  **tutti** i `tool_calls` di **tutti** gli `AIMessage`, non dall'ultimo.
- **Una risposta corretta ma non diretta.** Alla domanda «posso piantare **adesso** i bulbi di
  tulipano?», con business date 12 ottobre, l'agente risponde «può iniziare a piantarli da metà
  ottobre in poi, non prima». È corretto — la guida dice «da metà ottobre a fine novembre» — ed
  è prudente sul confine della finestra, ma non risponde con il sì che il cliente cerca.
- **Decisione: non si tocca il prompt adesso.** La fase 7 è la sede prevista per gli interventi
  correttivi, e ha il confronto prima/dopo che li rende verificabili. Modificare il prompt ora,
  su una singola osservazione qualitativa e senza metrica, è il modo classico di peggiorare
  credendo di migliorare — lo stesso errore contro cui ADR-046 mette in guardia a proposito
  della scelta della metrica.
- **Come usarla in fase 7**: se `AnswerRelevancy` o il giudizio sui casi `agronomic_advice`
  risulteranno bassi, questa è la prima ipotesi da verificare, ed è già formulata.

## ADR-054 — Il checkpointer dichiara i tipi che serializza

- **Contesto**: eseguendo la prima conversazione multi-turno è comparso un avviso di
  `langgraph`: «Deserializing unregistered type `greenthumb.schemas.AgentOutput` from
  checkpoint. **This will be blocked in a future version**».
- **Perché non è rumore**: l'output strutturato viene salvato nel checkpoint a ogni turno.
  Quando quella versione arriverà, le conversazioni multi-turno smetteranno di funzionare — e
  il notebook consegnato oggi verrà eseguito mesi dopo, su un runtime Colab che installa le
  versioni del momento.
- **Decisione**: `build_checkpointer()` costruisce l'`InMemorySaver` con un
  `JsonPlusSerializer(allowed_msgpack_modules={("greenthumb.schemas", "AgentOutput")})`.
  Effetto secondario desiderabile: si esce dalla modalità permissiva, che accetta in
  deserializzazione **qualunque** tipo.
- **Dettaglio che è costato un giro**: l'allowlist vuole la coppia `(modulo, classe)`, non le
  parti del percorso del modulo. Il primo tentativo con `("greenthumb", "schemas")` ha
  trasformato l'avviso in un **blocco effettivo** — il che, almeno, ha reso l'errore
  immediatamente visibile invece di lasciarlo latente.
- **Conseguenze**: tre test di regressione, incluso un round-trip completo di `AgentOutput`
  attraverso il serializzatore.

## ADR-055 — Log dello scatto della summarization, con i numeri che l'hanno deciso

- **Contesto**: il middleware non lascia alcun segnale di aver riassunto: sostituisce la lista
  dei messaggi e basta. Il PLAN chiedeva di loggare lo scatto per la demo del notebook.
- **Decisione**: `LoggingSummarizationMiddleware` sottoclassa il middleware e sovrascrive
  `before_model`, che è **pubblico** e restituisce un dizionario esattamente quando ha
  riassunto, `None` altrimenti. Nessun aggancio a interni privati.
- **La riga di log riporta i token, non solo i messaggi**, ed è questa scelta ad aver reso
  visibile ADR-056: la prima esecuzione stampava «5 messaggi (387 token)» contro una soglia di
  1500, e quel numero incoerente era l'unico indizio disponibile. Un log che avesse riportato
  solo il conteggio dei messaggi non avrebbe detto nulla.
- **Conseguenze**: `scripts/demo_memory.py` usa lo stesso log per la demo del notebook.

## ADR-056 — La soglia di summarization si confronta col totale riportato dal provider

- **Contesto**: SPEC §9 fissava il trigger a 2500 token, intendendo implicitamente i token
  della conversazione.
- **Scoperta**: `_should_summarize` scatta se **una qualsiasi** delle due condizioni è vera:
  i token della lista messaggi, **oppure** il `total_tokens` che il provider riporta
  nell'ultima risposta — e quel totale comprende **system prompt e schemi dei tre tool**, non
  solo la conversazione.
- **Misura** (nessuna summarization attiva, per osservare la crescita reale):

  | Turno | Messaggi | `total_tokens` riportati per chiamata |
  |---|---|---|
  | 1 | 4 | **2583**, 2814 |
  | 2 | 8 | 2867, 3816 |
  | 3 | 12 | 3863, 4758 |
  | 4 | 16 | 4794, 5486 |

- **Conseguenza del valore originale**: con 2500, **la primissima chiamata supera già la
  soglia**. La summarization sarebbe scattata prima di ogni singola chiamata al modello, dal
  primo turno: una chiamata LLM aggiuntiva ogni volta, e conversazioni di due battute
  compattate senza alcuna ragione.
- **Perché nessun test lo avrebbe rilevato**: i test di memoria sarebbero stati *più* verdi,
  non meno, perché la summarization scatta sempre. Il sintomo sarebbe arrivato dalla bolletta.
- **Decisione**: trigger a **8000** token. Con un pavimento di ~2583 e una crescita di circa
  1000 token per turno, la summarization scatta attorno al sesto turno: una conversazione
  lunga per il customer care, senza compattare quelle brevi.
- **Guardia**: un validatore rifiuta valori sotto 3000, citando il pavimento misurato e
  spiegando cosa accadrebbe. Stessa logica di ADR-043: un valore che rende patologico un
  meccanismo non deve essere un valore ammissibile. Verso l'alto resta libero.
- **Alternative scartate**: trigger sui messaggi (deterministico e immune al problema, ma devia
  da SPEC §9 che parla di token); frazione della finestra di contesto (si adatta al modello, ma
  dipende dal fatto che LiteLLM esponga il limite attraverso OpenRouter, e rende la soglia
  illeggibile nella relazione); tenere 2500 dichiarandolo deliberato (nessun beneficio).
- **Nota per la fase 7**: le conversazioni `memory` del dataset devono superare gli 8000 token
  riportati, cioè contare almeno sei turni, altrimenti testeranno una summarization che non è
  mai scattata — l'errore di ADR-028, in una forma nuova.

## ADR-057 — La memoria non serve se il prompt non la considera conoscenza

- **Contesto**: con il trigger corretto, il test di memoria è diventato rosso su una cosa che
  la fase precedente non aveva mostrato. Il riassunto **conteneva** «Ordine 1042» ed era in
  contesto, eppure alla domanda «mi ricorda qual era il numero del mio ordine?» l'agente
  rispondeva: «non ho accesso diretto ai dati personali o agli ordini senza che lei me li
  fornisca».
- **Diagnosi**: non è un difetto della memoria, è il system prompt. La regola di SPEC §8 punto
  5 — «se il cliente parla del suo ordine senza dare il numero, chiediglielo» — veniva applicata
  all'**ultimo messaggio** invece che alla conversazione, e la regola di grounding «non
  inventare mai numeri d'ordine» faceva il resto, spingendo il modello a trattare un dato già
  fornito dal cliente come un'invenzione da evitare.
- **Decisione**: nuova sezione «Cosa sai già» nel prompt, che dichiara la storia della
  conversazione — **riassunto incluso** — parte di ciò che l'agente sa, e precisa che
  riprendere un numero d'ordine già fornito non è inventare. La regola di chiarimento è stata
  riscritta con la condizione giusta: chiedere solo se il numero «non compare da nessuna parte
  nella conversazione».
- **Perché questa modifica al prompt si fa ora e quella di ADR-053 no**: qui c'era un test
  rosso che asserisce un requisito della Definition of Done della fase, e la modifica lo fa
  passare in modo verificabile. In ADR-053 c'era una singola osservazione qualitativa senza
  metrica, e la sede giusta resta la fase 7.
- **Conseguenze**: sette test di memoria con LLM reale verdi, compresa la sopravvivenza del
  numero d'ordine del primo turno. Lezione generale per la relazione: **un meccanismo di
  memoria può funzionare perfettamente e non servire a nulla**, se le istruzioni dell'agente
  non gli dicono che quella memoria è conoscenza legittima.

## ADR-058 — Un turno senza alcun tool non può dichiarare confidence alta

- **Contesto**: SPEC §5 elenca tre casi per il cap della confidence: risposta basata sui soli
  dati ordine (nessun cap), retrieval usato (cap dagli score), retrieval senza risultati sopra
  soglia (cap `low`). **Manca il quarto caso**: il turno in cui non è stato invocato alcun tool.
  Non è un'eventualità remota — è la forma di tre comportamenti legittimi e previsti: il rifiuto
  cortese di una domanda fuori ambito (SPEC §8), la domanda di chiarimento quando la richiesta è
  ambigua (SPEC §8 punto 5), e la risposta di cortesia a un ringraziamento.
- **Il problema**: è anche la forma del fallimento più grave, cioè il modello che risponde a una
  domanda di giardinaggio attingendo alla propria conoscenza invece che alla KB, che la regola di
  grounding vieta esplicitamente. Dal punto di vista di `response.py` i due casi sono
  **indistinguibili**: entrambi sono turni senza alcun `ToolMessage`. Distinguerli richiederebbe
  di leggere il testo della risposta e giudicarlo, che è esattamente ciò che ADR-002 rifiuta di
  fare nel livello deterministico.
- **Decisione**: cap a `medium`. Quando due casi hanno la stessa impronta osservabile, il cap si
  decide sul peggiore dei due.
- **Alternative scartate**:
  - *nessun cap* (`high`): lascerebbe che una risposta non ancorata si presenti al cliente con
    la massima autorevolezza. È il caso peggiore della coppia, e non è accettabile che sia anche
    il più sicuro di sé.
  - *cap a `low`*: penalizza il comportamento corretto. Una domanda di chiarimento è la *migliore*
    risposta possibile a una richiesta ambigua, e marcarla `low` insegna all'evaluation che
    chiedere è una debolezza. Confonde inoltre questo caso con il retrieval a vuoto, che è
    genuinamente `low` perché lì il sistema ha cercato e non ha trovato.
  - *classificare leggendo la risposta*: reintroduce un giudizio probabilistico nel livello che
    esiste per non averne.
- **Conseguenze**: il cap resta un tetto, non un'assegnazione. Se il modello propone `low` su un
  rifiuto, la risposta resta `low` (`lower_of`): il cap non alza mai la confidence, la limita.
  SPEC §5 estesa con il quarto caso. Coperto da test su trace costruite a mano.

## ADR-059 — Il testo dei chunk viaggia nell'artifact, duplicato dal contenuto

- **Contesto**: SPEC §7 prescriveva per il tool RAG un artifact di forma
  `{doc_id, score, chunk_id}`, sufficiente all'intersezione di ADR-002. Le metriche RAGAS
  (Faithfulness e ContextPrecision) vogliono però i `retrieved_contexts`, cioè **il testo** dei
  chunk recuperati, non i loro identificatori: la faithfulness misura se la risposta è
  sostenuta dai contesti, e senza i contesti non c'è nulla da misurare.
- **Decisione**: aggiungere `text` a ogni voce dell'artifact, duplicando ciò che già compare nel
  contenuto formattato per il modello.
- **Perché duplicare invece di ricavare**: l'alternativa è ricostruire i contesti facendo il
  parsing del testo mostrato al modello. Quel testo esiste per essere letto da un modello, e il
  suo layout cambierà la prima volta che si ritocca la formattazione del tool. Un parser su di
  esso si romperebbe **in silenzio**, e il sintomo sarebbe un punteggio di faithfulness calcolato
  su contesti troncati o vuoti: un *numero*, non un errore. Un numero sbagliato in una relazione
  di valutazione è peggio di un'eccezione.
- **Perché questa duplicazione è sicura, a differenza di quella di ADR-048**: i due consumatori
  (il modello e le metriche) leggono copie prodotte **nella stessa espressione, dalla stessa
  lista `hits`**. Non esistono due punti del codice che possano divergere nel tempo, che è
  l'unico vero costo della duplicazione.
- **Alternative scartate**: rieseguire il retrieval nel runner dell'evaluation (due ricerche per
  turno, e nulla garantisce che la seconda restituisca ciò che l'agente ha visto: l'indice può
  essere stato ricostruito fra l'esecuzione e il calcolo delle metriche); far salvare i contesti
  al modulo di retrieval attraverso un canale laterale (stato globale, e ADR-047 ha già mostrato
  cosa costa un'informazione che viaggia per vie non dichiarate).
- **Conseguenze**: l'artifact cresce di circa 519 caratteri per chunk (la media misurata in
  ADR-045), ma **nessuno lo paga in token**: l'artifact non viene mai inviato al modello.
  `ChatTurn.retrieved_contexts` lo espone all'evaluation in una riga. SPEC §7 aggiornata.

## ADR-060 — Un solo registro delle escalation, condiviso fra il tool e il servizio

- **Contesto**: il tool di escalation **scrive** i ticket, il servizio **legge** il registro per
  calcolare `needs_human` (ADR-008). Entrambi hanno bisogno di un `EscalationsRepository`, e il
  primo cablaggio ne costruiva due: uno dentro `build_default_agent` per il tool, uno nel
  servizio.
- **Cosa ha trovato il test di integrazione**: `escalate_to_human` era stato invocato e il
  ticket scritto, eppure `needs_human` tornava `False`. In produzione le due istanze puntano allo
  stesso file, perché entrambe leggono il percorso dalla stessa configurazione: funzionava **per
  coincidenza di configurazione invece che per costruzione**. Il test passava un percorso
  temporaneo a una sola delle due, le due sono divergite, e il tool ha scritto il ticket in un
  file mentre il servizio ne leggeva un altro.
- **Decisione**: `build_chat_service` crea **un** registro e lo passa a entrambi;
  `build_default_agent` lo accetta come parametro. Lo stesso vale per l'istanza del modello, che
  veniva anch'essa costruita due volte — una per l'agente e una per il middleware di
  summarization — con il rischio speculare di due configurazioni divergenti.
- **Alternative scartate**: lasciare che entrambi leggano il percorso dalla configurazione,
  documentando che devono concordare (un'invariante mantenuta per convenzione è quella che si
  rompe appena qualcuno aggiunge un parametro: è appena successo); un singleton a livello di
  modulo (stato globale, e i test non potrebbero più isolare il file).
- **Conseguenze**: ciò che rende `needs_human` deterministico non è solo che derivi da un file
  invece che da un giudizio dell'LLM — è che ci sia **un** file e un solo oggetto che lo possiede.
- **Nota di metodo per la relazione**: il difetto era nel codice di produzione ed era invisibile
  in produzione. Il test non ha trovato un errore in sé stesso: ha trovato un errore che solo una
  configurazione diversa poteva esporre. È il motivo per cui a un test va **concesso** di
  configurare il sistema in modo diverso dalla produzione, invece di imitarla fedelmente: un test
  che riproduce anche le coincidenze della produzione eredita anche i suoi punti ciechi.

## ADR-061 — Un test che conta i messaggi non può esprimere il limite in turni

- **Contesto**: il test di memoria «il conteggio dei messaggi smette di crescere» confrontava il
  totale con `2 * numero_di_turni + 2`. È **passato per due fasi** e poi è diventato rosso a
  fine fase 6, su una riesecuzione **senza una riga di codice cambiata**: `max([6, 6, 6, 10])`
  contro un limite di 10.
- **Causa misurata**: il limite è espresso in *turni*, la grandezza misurata è in *messaggi*, e
  il cambio di unità nasconde un fattore che non controlliamo. Replaying la stessa
  conversazione (script usa-e-getta, una sola esecuzione) le forme dei turni sono:

  | Turno | Messaggi | Forma |
  |---|---|---|
  | 1 | 6 | human → AI(`get_order_status`) → tool → AI(`search_knowledge_base`) → tool → AI |
  | 2 | 6 | summary → … → human → AI |
  | 3 | 8 | summary → … → human → AI(`search_knowledge_base`) → tool → AI |
  | 4 | 6 | summary → … → human → AI(`search_knowledge_base`) → tool → AI |

  Un singolo turno contribuisce 2 messaggi se risponde da sé, 4 con un giro di tool, **6 con
  due giri**. Il turno 1 ne usa due in sequenza — e si noti che qui `get_order_status` e
  `search_knowledge_base` **non** sono stati emessi insieme, contrariamente a quanto osservato
  in ADR-053 su un altro prompt: il raggruppamento delle chiamate è una scelta del modello, non
  una garanzia. Con temperatura 0 e fornitori ruotati da OpenRouter (ADR-030), il numero di giri
  varia fra esecuzioni identiche.
- **Decisione**: asserire il limite che il middleware garantisce davvero. Tutto ciò che precede
  il turno in corso deve stare nella finestra `keep` più il messaggio occupato dal riassunto:
  `len(messages) - len(messages_of_current_turn(messages)) <= keep + 1`. Il confine del turno
  corrente è individuato da `messages_of_current_turn`, la stessa funzione che `response.py` usa
  per raccogliere le evidenze — nessuna seconda definizione di «turno» da tenere allineata
  (ADR-006).
- **Alternative scartate**: alzare il limite a 12 (sposta la soglia di flakiness senza
  rimuoverla: con tre giri di tool un turno ne aggiunge 8); derivare il limite da
  `agent_max_iterations` (corretto ma vacuo: con 8 iterazioni il limite diventa così alto da
  non escludere nulla); ripetere la conversazione senza summarization per confrontare i due
  conteggi (dimostrerebbe di più, ma raddoppia il costo di ogni esecuzione dei test di memoria
  per un'informazione già registrata nella tabella di ADR-056).
- **Conseguenze**: il test non dipende più da quante volte il modello decide di usare un tool.
- **Lezione per la relazione**: un test verde non è una prova che l'asserzione sia giusta —
  può essere una prova che il campione non ha ancora incontrato il caso che la smentisce.
  Questo è passato per due fasi con un limite che non misurava il meccanismo sotto test.

## ADR-062 — Venti conversazioni, non diciotto: il PLAN era rimasto indietro

- **Contesto**: tre documenti davano tre numeri. SPEC §10.1 e ADR-016 dicono **20**
  conversazioni, il PLAN alla fase 7 ne chiedeva **18**, e la traccia d'esame ne impone almeno
  15. Non un dettaglio di conteggio: ADR-016 aveva alzato il numero a 20 **per una ragione
  precisa**, cioè portare `escalation` e `multi_tool` a tre conversazioni ciascuna, perché
  l'enum `reason` ha sette valori e due sole conversazioni non li coprivano.
- **Decisione**: 20 conversazioni, come da ADR-016, e la riga del PLAN corretta.
- **Alternative scartate**: 18 per aderenza al PLAN (farebbe perdere proprio la copertura che
  ADR-016 esisteva per ottenere, e il risparmio sarebbe di due conversazioni su una spesa
  dell'ordine del dollaro).
- **Conseguenze**: distribuzione finale 3/3/2/2/3/3/2/2 su `product_info`,
  `agronomic_advice`, `order_status`, `returns_policy`, `multi_tool`, `escalation`, `memory`,
  `edge_cases`, per 43 turni e 12 conversazioni multi-turno (il minimo richiesto era 6).
  Un test asserisce la distribuzione, così il numero non può più divergere fra documenti.
- **Nota di metodo**: quando due documenti del progetto si contraddicono, vince quello che
  porta con sé la motivazione. Un numero senza ragione è un refuso; un numero con un ADR
  dietro è una decisione.

## ADR-063 — Il dataset è verificato contro i dati veri, non contro una copia delle attese

- **Contesto**: `eval/conversations.jsonl` è ground truth: ogni metrica di SPEC §10.3 misura
  l'agente **contro** questo file. Un `doc_id` sbagliato o un numero d'ordine inesistente non
  solleverebbe nulla da nessuna parte: abbasserebbe `source_recall` in silenzio, e il
  `summary.md` riporterebbe il difetto come un **risultato sull'agente** invece che come un
  errore del dataset. È lo stesso rischio di ADR-059 — un numero sbagliato in una relazione
  di valutazione è peggio di un'eccezione.
- **Decisione**: `tests/test_eval_dataset.py` verifica il dataset contro la knowledge base e
  gli ordini **reali**, caricati con gli stessi moduli che usa l'agente, non contro un elenco
  di attese ricopiato a mano. Ogni `expected_sources` deve esistere fra i `doc_id` caricati da
  `load_knowledge_base`, ogni numero d'ordine di quattro cifre citato dal cliente deve
  risolvere in `OrdersRepository` — e l'ordine 9999 degli `edge_cases` deve **non** esistere,
  altrimenti il caso limite non esiste. I nomi dei tool sono importati dai moduli dei tool
  (`TOOL_NAME`), non scritti come stringhe.
- **Tre difetti trovati subito**, ciascuno invisibile a un'ispezione a vista:
  1. due turni dichiaravano una `expected_sources` ma non `search_knowledge_base` fra i tool
     attesi — una fonte senza il recupero che la produce è un'attesa impossibile, che avrebbe
     prodotto un falso negativo su `source_recall`;
  2. un terzo turno aveva lo stesso difetto con tre tool in gioco, scoperto solo dopo la
     correzione dei primi due;
  3. una `reference_answer` di otto parole, troppo magra perché un giudice LLM potesse
     distinguere una risposta corretta dal rumore.
- **Un'asserzione sbagliata era nel test, non nel dataset**: il controllo sulla copertura
  dell'escalation pretendeva che i turni che escalano stessero *solo* nelle categorie
  `escalation` ed `edge_cases`. Ne esiste però uno deliberato in `memory`, ed è il punto di
  quella conversazione: verificare che `needs_human` sopravviva alla summarization (ADR-008).
  Corretto il test in inclusione (`⊆`) invece di uguaglianza.
- **Conseguenze**: 17 test, nessuna chiamata LLM. Il dataset non può divergere dai dati senza
  che `make test` lo dica. Vale la lezione di ADR-037: un validatore ha valore solo se qualcosa
  può fallire, e qui è fallito tre volte alla prima esecuzione.

## ADR-064 — `expected_tools` si misura per inclusione, non per uguaglianza

- **Contesto**: la metrica `tool_selection_accuracy` di SPEC §10.3 confronta i tool invocati
  con quelli attesi. Confrontare i due **insiemi per uguaglianza** sembra la lettura naturale.
- **Perché non funziona**: ADR-061 ha misurato che il numero di giri di tool su uno stesso
  turno **varia fra esecuzioni identiche**, perché il raggruppamento delle chiamate è una
  scelta del modello (ADR-053 lo aveva visto raggruppare, ADR-061 lo ha visto separare). Un
  agente che ricontrolla un ordine già discusso qualche turno prima sta facendo la cosa
  giusta — l'alternativa è fidarsi del riassunto per un dato che il tool può rileggere — ma con
  l'uguaglianza quel comportamento corretto conterebbe come errore.
- **Decisione**: `expected_tools` elenca i tool **senza i quali il turno non può essere
  corretto**, e la metrica misura `expected ⊆ invocati`. Un tool in più non penalizza; uno
  mancante sì.
- **Alternative scartate**: uguaglianza fra insiemi (misurerebbe la variabilità del modello
  invece della sua scelta, e renderebbe il confronto prima/dopo della fase 7 illeggibile);
  elencare in `expected_tools` ogni tool plausibile (sposta il giudizio dentro il ground truth
  e rende la metrica vacua, perché tutto diventa atteso).
- **Conseguenze**: la metrica risponde alla domanda «l'agente ha raccolto le evidenze che
  servivano?» e non «ha fatto esattamente i passi che avevo immaginato?». Due turni dei casi
  `memory` hanno `expected_tools` vuoto a ragion veduta: alla domanda «qual era il numero del
  mio ordine?» rispondere dalla memoria è legittimo tanto quanto rileggere l'ordine, e imporre
  l'uno o l'altro misurerebbe una preferenza nostra, non un requisito.

## ADR-065 — Ogni esecuzione dell'evaluation ha il suo registro delle escalation

- **Contesto**: `needs_human` non deriva da un giudizio dell'LLM ma dal registro delle
  escalation della sessione (ADR-008, ADR-060). Il registro è un file, `escalations.jsonl`,
  e in esercizio è **lo stesso file** per tutte le conversazioni.
- **Il rischio**: la fase 7 esegue l'evaluation **due volte**, prima e dopo un intervento
  correttivo, e confronta i numeri. Se le due esecuzioni condividessero il registro, la
  seconda partirebbe con i ticket della prima già scritti. Oggi i `session_id` sono generati
  a caso a ogni esecuzione, quindi l'idempotenza per sessione+motivo non farebbe collidere
  nulla — ma è di nuovo un'invariante tenuta per **coincidenza** invece che per costruzione,
  esattamente il difetto che ADR-060 ha chiuso nel servizio. Basterebbe fissare i
  `session_id` per renderli riproducibili (una cosa sensata da volere) perché il confronto
  prima/dopo diventasse silenziosamente falso.
- **Decisione**: il runner crea un registro in una directory temporanea, valido per quella
  sola esecuzione, e lo passa a `build_chat_service`. Il file di esercizio non viene toccato.
- **Alternative scartate**: cancellare `escalations.jsonl` prima di ogni esecuzione
  (distrugge dati di esercizio per un'esigenza dell'evaluation, e sarebbe irreversibile);
  usare `session_id` casuali e fidarsi (è la coincidenza di cui sopra); un registro in memoria
  per i test (il percorso del file fa parte di ciò che si vuole esercitare).
- **Conseguenze**: una riesecuzione dell'evaluation è indipendente dalle precedenti **per
  costruzione**. Effetto collaterale utile: l'evaluation non sporca il registro di esercizio
  con ventisei ticket finti.

## ADR-066 — Lo strumento di misura si testa come il sistema misurato

- **Contesto**: l'harness di evaluation è ciò con cui si misura l'agente. Un harness
  sbagliato non produce un errore: produce **numeri**, e quei numeri finiscono nella
  relazione come affermazioni sull'agente. È lo stesso argomento di ADR-059 — un numero
  sbagliato in una relazione di valutazione è peggio di un'eccezione — applicato allo
  strumento invece che al dato.
- **Decisione**: `tests/test_eval_harness.py`, 17 test, **nessuna chiamata LLM**. Il runner
  è pilotato da un servizio finto che risponde da copione, le metriche deterministiche sono
  alimentate con trace costruite a mano, l'aggregazione delle metriche giudicate è testata
  senza giudice, e il report è reso dai file di punteggio. Nessun test chiede un modello.
- **Quattro moduli in più rispetto a SPEC §3**, ciascuno per eliminare una duplicazione:
  - `eval/dataset.py` — il dataset ha due lettori, il runner e i test;
  - `eval/traces.py` — la forma della trace ha quattro lettori, e quattro moduli che
    concordano su un nome di chiave lo fanno finché uno smette (ADR-006);
  - `eval/judges.py` — il wiring verificato in ADR-033 è condiviso fra RAGAS e DeepEval, e
    l'opt-out dalla telemetria di DeepEval (ADR-018) avviene qui, una volta, così nessun
    modulo può dimenticarlo;
  - `eval/report.py` — SPEC §10.4 chiede `summary.md` ma SPEC §3 non assegna a nessuno il
    compito di scriverlo.
- **Smoke run, perché il codice non provato non è codice che funziona**: `make eval-smoke`
  replica **una** conversazione a turno singolo attraverso l'intera pipeline. Eseguito: le
  sei metriche deterministiche, Faithfulness (1.0), ContextPrecisionWithReference (~1.0),
  AnswerRelevancy (1.0), GEval escalation (0.9, con motivazione in italiano) e
  KnowledgeRetention (1.0) girano tutte, e il report si genera. Costo misurato: sei chiamate.
- **Conseguenze**: l'harness è verificato prima di spendere l'esecuzione completa. Da
  ricordare: il pacchetto `eval` si invoca con `python -m eval.<modulo>` dalla radice del
  repository — eseguire un file dell'harness per percorso non trova il pacchetto, e il
  Makefile usa già la forma corretta.

## ADR-067 — Una metrica dichiara la sua popolazione, e un valore assente non è uno zero

- **Contesto**: tre scelte di misurazione che sembrano dettagli e decidono se i numeri
  significhino qualcosa.
- **Decisione (a) — ogni metrica dichiara su quali turni è definita, e un insieme vuoto
  vale `None`, non 1.0 né 0.0.** `source_recall` si misura sui turni che attendono fonti,
  `tool_selection_accuracy` su quelli che attendono tool. Includere i turni senza attese
  gonfierebbe il punteggio con passaggi gratuiti: un rifiuto fuori ambito non attende tool,
  quindi "ha usato i tool attesi" è vero in modo vacuo. Un `None` esplicito nel report dice
  «questa metrica qui non si applica» invece di far sembrare perfetto ciò che non è stato
  misurato.
- **Decisione (b) — un punteggio che il giudice non ha prodotto è escluso dalla media e
  contato a parte.** Un'eccezione del giudice (un `402`, un timeout, un parsing fallito) è
  un'informazione sul giudice, non sull'agente. Mediarla come zero abbasserebbe il
  risultato dell'agente per un guasto che non lo riguarda, e il colpevole sbagliato è il
  peggior esito possibile per una relazione di valutazione. Il runner e le metriche quindi
  **non** si fermano sul primo errore: perdere un punteggio è recuperabile, perdere
  un'esecuzione intera no.
- **Decisione (c) — `schema_validity` si riporta, dichiarando che è quasi vacua.** Il
  livello deterministico costruisce `ChatResponse` da sé e un errore di parsing diventa il
  fallback di cortesia (SPEC §5): una risposta non valida **non può** raggiungere un
  chiamante, quindi la metrica vale 1.0 per costruzione. È richiesta da SPEC §10.3 e un
  valore inferiore segnalerebbe una regressione reale, perciò resta — accompagnata da
  `answered without fallback`, che è la cifra che porta davvero informazione sui guasti.
- **Una metrica aggiunta**: `summarization fired (memory)` verifica che le conversazioni
  `memory` abbiano davvero superato la soglia. Senza, un test di memoria superato non
  dimostra nulla: l'entità del primo turno sopravvive banalmente se non è stato riassunto
  niente (ADR-028, ADR-056). È l'unico modo di distinguere «la memoria regge» da «la memoria
  non è stata messa alla prova».
- **Conseguenze**: il report distingue tre esiti — rispettato, non rispettato, non
  applicabile — invece di due. Costa una colonna in più e rende i numeri leggibili.

## ADR-068 — Due osservazioni dallo smoke run, da portare nell'analisi

- **Il retrieval ha restituito quattro chunk dello stesso documento.** Sulla domanda sulle
  forbici, i quattro risultati di top-k sono tutti sezioni di
  `products/forbici_potatura_bypass.md`, con score 0.8795, 0.8712, 0.8681 e 0.8515. Per
  quella domanda è il comportamento giusto — la risposta sta lì — ma su una domanda a due
  facce (un prodotto **e** una policy) il top-k può esaurirsi su un solo documento e lasciare
  la seconda metà della domanda senza fonte. È un'ipotesi concreta per i casi
  `multi_tool` e `returns_policy` dell'analisi, e un intervento misurabile: ricerca con
  diversificazione (MMR) oppure due ricerche con `doc_type` diverso.
- **GEval ha dato 0.9, non 1.0, a un'escalation corretta.** La motivazione in italiano è
  pertinente e il punteggio è alto, ma conferma che il criterio discrimina invece di
  saturare — il contrario del problema di ADR-033, dove `AnswerRelevancy` dava 0.5 a una
  risposta corretta.
- **Decisione: nessun intervento adesso.** Vale la disciplina di ADR-053: la sede degli
  interventi correttivi è il confronto prima/dopo, e la metrica con cui si misura un
  intervento va scelta **prima** di vedere i risultati (ADR-046). Queste due osservazioni
  sono registrate come ipotesi già formulate, non come modifiche già fatte.

## ADR-069 — L'analisi sta in un file che il report include, non dentro il report

- **Contesto**: `eval/results/summary.md` è generato da `eval/report.py`, perché ogni cifra
  deve venire da un file che chi legge può aprire. SPEC §10.4 chiede però anche l'analisi dei
  tre casi peggiori e il confronto prima/dopo, che **non si possono calcolare**.
- **Il difetto della prima stesura**: il generatore inseriva dei segnaposto HTML da riempire
  a mano. Funziona una volta: la seconda esecuzione del report — e la fase 7 ne prevede
  almeno due — riscrive il file e **cancella l'analisi**. Il pezzo meno riproducibile del
  report era custodito nel posto più volatile.
- **Decisione**: la prosa sta in `eval/results/analysis.md`, versionato e scritto a mano; il
  report lo include alla fine, verbatim. Se manca, il report lo dichiara mancante invece di
  omettere la sezione in silenzio.
- **Alternative scartate**: analisi dentro DECISIONS.md con un rimando (il report consegnato
  non sarebbe leggibile da solo); report scritto interamente a mano (ogni cifra diventa
  trascritta, cioè non verificabile); segnaposto più un avviso di non rigenerare (una
  convenzione che si rompe appena qualcuno rigenera).
- **Conseguenze**: `make eval` si può rieseguire quante volte serve senza perdere una riga di
  analisi. Due test coprono entrambi i casi, analisi presente e assente.

## ADR-070 — Prima esecuzione completa: i criteri di escalation sono elencati, non vincolanti

- **Contesto**: prima esecuzione dell'evaluation sulle 20 conversazioni, 43 turni, nessun
  fallback e nessuna risposta non conforme allo schema.

  | Metrica | Valore |
  |---|---|
  | `needs_human accuracy` | 86,0% (37/43) |
  | `tool selection accuracy` | 82,5% (33/40) |
  | `source recall` | 50,0% (14/28) |
  | `schema validity` | 100% (43/43) |
  | `answered without fallback` | 100% (43/43) |
  | `summarization fired (memory)` | **0% (0/2)** |
  | RAGAS Faithfulness | 0.754 (23 turni) |
  | RAGAS ContextPrecisionWithReference | 0.798 (23 turni) |
  | DeepEval AnswerRelevancy | 0.908 (43 turni) |
  | DeepEval GEval escalation | 0.692 (12 turni) |
  | DeepEval KnowledgeRetention | 1.000 (2 conversazioni) |

- **Diagnosi**: i sei errori su `needs_human` vanno in **due direzioni opposte** — due
  escalation di troppo su domande di policy a cui la KB risponde (conv_09#1 e conv_13#2
  hanno aperto un ticket *invece* di rispondere), quattro mancate dove la specifica le
  impone, fra cui un caso `safety` (conv_16#1, un cane che ingerisce un bulbo) gestito nel
  merito ma senza ticket e **senza invocare alcun tool**. Una regola applicata al contrario
  in metà dei casi non è una regola poco seguita: è una regola letta come facoltativa. Nel
  system prompt i sette criteri sono elencati, non vincolanti.
- **Il reperto più importante non è il più brutto**: `summarization fired (memory)` vale 0/2
  e `KnowledgeRetention` vale 1.000. Insieme, dimostrano che la retention perfetta non
  misura niente, perché la soglia di 8000 token non è mai stata superata — la trappola di
  ADR-028, ritrovata da una metrica scritta per smascherarla. La stima di ADR-056 («almeno
  sei turni») era ottimistica sui turni brevi.
- **Due artefatti di metrica, documentati e non corretti**: `faithfulness` e
  `context_precision` valgono 0.000 sulla categoria `edge_cases`, perché un rifiuto non
  contiene affermazioni da sostenere; `answer_relevancy` scende a 0.608 sulla stessa
  categoria, dove la risposta corretta è non rispondere. Escludere i rifiuti dalle
  popolazioni sarebbe legittimo, ma deciderlo **dopo** aver visto i numeri è la scelta della
  metrica a posteriori contro cui ADR-046 mette in guardia. Restano nei numeri come limite
  dichiarato.
- **Decisione**: un solo intervento correttivo, sul system prompt, sulla causa comune, con
  le metriche di giudizio dichiarate **prima** della seconda esecuzione: `needs_human
  accuracy` primaria, `escalation_correctness` secondaria, `tool selection accuracy` e
  `answer_relevancy` come guardie di regressione. `source recall` è esclusa dal giudizio
  perché un terzo dei suoi fallimenti dipende da `expected_sources` troppo stretti del
  dataset — a conv_06#1 l'agente ha citato una guida diversa che contiene la stessa scala di
  ore di sole, e la risposta è corretta. Le aspettative **non** sono state allargate a
  posteriori (ADR-045).
- **Costo misurato**: una esecuzione completa, agente più tre giudici, è costata circa 300
  chiamate.

## ADR-071 — L'intervento correttivo: criteri vincolanti, e i due costi che ha prodotto

- **Contesto**: ADR-070 aveva isolato una causa comune (criteri di escalation letti come
  facoltativi) e dichiarato le metriche di giudizio **prima** di intervenire, come ADR-046
  impone: `needs_human accuracy` primaria, `escalation_correctness` secondaria,
  `tool selection accuracy` e `answer_relevancy` come guardie di regressione.
- **Intervento**: un solo cambiamento, in `prompts.py`. La sezione sull'escalation diventa
  **due regole esplicite** — «se la knowledge base risponde, rispondi» e «se il caso ricade
  in uno di questi criteri, apri il ticket, sempre, anche quando hai già risposto nel
  merito» — più una riga nella regola di grounding: «cercare viene prima di affermare».

  | Ruolo | Metrica | Prima | Dopo |
  |---|---|---|---|
  | Primaria | `needs_human accuracy` | 86,0% (37/43) | **95,3% (41/43)** |
  | Secondaria | `escalation_correctness` | 0.692 | 0.725 |
  | Guardia | `tool selection accuracy` | 82,5% | 82,5% |
  | Guardia | `answer_relevancy` | 0.908 | **0.884** |
  | Fuori giudizio | `source recall` | 50,0% | 60,7% |
  | Fuori giudizio | Faithfulness / ContextPrecision | 0.754 / 0.798 | 0.846 / 0.833 |

- **Esito**: cinque dei sei turni che sbagliavano il flag sono corretti, compresi tutti e tre
  quelli di conv_16 (il caso `safety`, i bulbi ammuffiti, i tempi di presa in carico).
- **I due costi, dichiarati e non nascosti**:
  1. **una regressione introdotta da me**: conv_19#2, il secondo tentativo sull'ordine 9999
     con numero confermato, prima escalava e ora no. Probabile causa: la precisazione «al
     primo tentativo non escalare», accanto a due regole in grassetto, è stata letta come
     prevalente anche al secondo tentativo.
  2. **`answer_relevancy` −0.024**: dove l'agente ora apre un ticket, la risposta tende a
     diventare *solo* il ticket. Su conv_16#1 la parte informativa sulla tossicità del bulbo,
     presente nella prima esecuzione, è sparita. Rendere obbligatorio il ticket ha spostato il
     peso della risposta dal contenuto alla procedura: è la direzione del prossimo intervento,
     il ticket **in aggiunta** alla risposta e non al posto suo.
- **Come ho separato l'effetto del prompt dal rumore del fornitore**: OpenRouter smista fra
  fornitori a monte e il pinning non è implementabile via LiteLLM (ADR-030), quindi due
  esecuzioni identiche divergono — in questa fase se n'è visto un caso pulito, conv_01#1 che
  cerca nello smoke run e non cerca nella prima esecuzione completa, a prompt identico. Il
  criterio è la **direzione**: i cinque turni corretti sono esattamente il bersaglio
  dell'intervento e si muovono tutti dalla stessa parte; conv_06#2 e conv_17#2 sono invece
  peggiorati *nel senso contrario* alla modifica (una riga che impone di cercare non può far
  cercare meno), e vanno quindi attribuiti alla variabilità, non al prompt.
- **Difetto residuo, non corretto**: conv_09#1 continua ad aprire un ticket su una domanda di
  policy a cui la KB risponde. Una seconda iterazione è l'ipotesi naturale, ma la fase chiede
  **un** intervento misurato e lo ha prodotto; accumulare modifiche sullo stesso prompt costa
  una esecuzione completa per tentativo e porta al sovradattamento su venti conversazioni, a
  quel punto i numeri salgono e misurano sempre meno.
- **Conseguenza di metodo**: aver dichiarato le metriche prima ha funzionato come previsto.
  Fra i numeri disponibili, `faithfulness` (+0.092) e `source recall` (+10,7 pt) sono i più
  spettacolari, ed entrambi erano **esclusi dal giudizio** — il secondo perché un terzo dei
  suoi fallimenti dipende da aspettative troppo strette del dataset. Scegliendo la metrica
  dopo avrei dichiarato un successo più grande misurando in parte il mio stesso ground truth.

## ADR-072 — La soglia di summarization era tarata su una stima, non su una misura

- **Contesto**: in entrambe le esecuzioni `summarization fired (memory)` valeva **0/2** e
  `knowledge_retention` valeva **1.000**. La metrica scritta per smascherare il falso
  positivo di ADR-028 lo aveva smascherato: il punteggio perfetto di retention non misurava
  nulla, perché niente era stato riassunto.
- **Misura prima di agire**, ricostruendo la lista dei messaggi dalle trace e contandola con
  lo stesso `token_counter` del middleware, offline e senza spendere una chiamata:

  | | token di conversazione | con system prompt |
  |---|---|---|
  | conv_17, 7 turni | 2 892 | ~4 466 |
  | conv_18, 6 turni | 2 374 | ~3 948 |

  Contro una soglia di 8 000. **La premessa di ADR-056 era sbagliata in modo sostanziale**:
  stimava ~1 000 token per turno, la crescita reale è ~600, e alcuni turni ne aggiungono
  quasi nulla (il settimo di conv_17 ne aggiunge 54). Con 8 000 la summarization scattava
  intorno al **dodicesimo** turno.
- **Decisione**: intervento doppio. Soglia **ricalibrata a 6 000** sulla crescita misurata —
  resta sopra il pavimento di ~2 583 della prima chiamata, quindi non scatta sulle
  conversazioni brevi, e cade intorno all'ottavo turno — e conversazioni `memory` portate a
  **10 turni** ciascuna.
- **Alternative scartate**: allungare a 13 turni lasciando la soglia a 8 000 (farebbe passare
  la metrica senza correggere la taratura, e metterebbe 26 turni su 56 in due sole
  conversazioni); solo ricalibrare (le conversazioni resterebbero corte per una categoria che
  deve dimostrare la memoria lunga); non toccare nulla (la retention continuerebbe a
  riportare 1.000 senza misurare niente).
- **Esito**: `summarization fired (memory)` passa a **2/2**, la summarization scatta cinque
  volte fra le due conversazioni, e i turni di retention recuperano l'entità del primo turno
  *dopo* il riassunto. `knowledge_retention` **scende** da 1.000 a 0.950 (conv_17 1.0,
  conv_18 0.9), e questa discesa è il risultato buono: per la prima volta il numero misura il
  meccanismo che dichiara di misurare.
- **Riesecuzione parziale, perché i giudici sono la parte cara**: `--only` e `--merge` sul
  runner, `--only` sulle metriche giudicate, con fusione per conversazione **e metrica** —
  un modulo che calcola due metriche non deve cancellare quella che non ha ricalcolato. Venti
  turni rigiocati invece di cinquanta. Un campo `run_label` su ogni trace rende la provenienza
  delle righe verificabile invece di nasconderla, e ha un default, così le trace scritte prima
  che esistesse si caricano ancora.
- **Avvertenza di lettura**: i denominatori sono cambiati (`source recall` da 28 a 35 turni,
  `tool selection` da 40 a 47), quindi le percentuali su 50 turni **non** sono confrontabili
  turno per turno con quelle su 43. Il confronto dell'intervento sul prompt resta sui due
  stati a 43 turni, conservati in `eval/results/before/` e `eval/results/after/`.
- **Nota su un vecchio difetto ritrovato**: il `.env` locale conteneva ancora
  `GREENTHUMB_SUMMARY_TRIGGER_TOKENS=8000` e sovrascriveva il nuovo default. È la terza
  manifestazione del problema di ADR-043: un valore di configurazione copiato una volta e
  dimenticato continua a vincere sui default calibrati. Il validatore protegge dal basso, non
  dal disallineamento.

## ADR-073 — Le trace non sono un artefatto rigenerabile, e vanno versionate

- **Contesto**: `.gitignore` elencava `eval/results/traces.jsonl` fra gli «artefatti
  generati, rigenerabili», accanto a `vector_store/`. Sembra la stessa categoria.
- **Non lo è**. Il vector store si ricostruisce con `make index`, gratis e identico. Una
  trace si ricostruisce con ~300 chiamate LLM e **viene diversa**, perché OpenRouter smista
  fra fornitori a monte (ADR-030). Non è un artefatto di build: è un **verbale di misura**.
  E SPEC §10.2 promette che le metriche si possono ricalcolare senza rieseguire l'agente —
  una promessa che vale solo per chi ha il file.
- **Il danno si è già verificato**: le trace della seconda esecuzione, quella che misura
  l'effetto dell'intervento sul prompt, **non esistono più**. Non erano committate per via di
  quella regola, e la riesecuzione parziale le ha sovrascritte. I punteggi restano, le
  risposte turno per turno no. È documentato in `eval/results/after/README.md` invece di
  essere lasciato scoprire a chi cerca il file.
- **Decisione**: rimossa la riga da `.gitignore`, con un commento che spiega perché non va
  rimessa; `eval/results/traces.jsonl` è versionato (127 KB). Resta ignorato
  `eval/results/smoke_traces.jsonl`, che è davvero usa-e-getta.
- **Conseguenze**: chi clona il repository può ricalcolare ogni metrica senza spendere una
  chiamata, e il notebook di consegna può caricare risultati reali (SPEC §13 punto 8) su un
  runtime pulito. Lezione generale: «generato» e «rigenerabile» non sono sinonimi, e la
  differenza si misura in costo e in riproducibilità.

## ADR-074 — L'API tiene il contratto a quattro campi anche quando qualcosa si rompe

- **Contesto**: SPEC §11 fissa il corpo di `POST /chat` a **esattamente** i quattro campi di
  `ChatResponse`, come nell'esempio della traccia. Tutto ciò che il chiamante ha comunque
  bisogno di sapere non può quindi stare nel corpo.
- **Decisione**: due header. `X-Session-Id` restituisce la conversazione, generata dal server
  quando il client non la fornisce; `X-Fallback: true` segnala il ripiego su guasto del
  provider (ADR-009). Un test asserisce `set(body) == {"answer", "confidence", "sources",
  "needs_human"}`: un campo in più romperebbe il contratto quanto una risposta sbagliata, e
  l'uguaglianza fra insiemi è l'unica asserzione che lo cattura.
- **Tre scelte di comportamento sui casi non nominali**:
  - **`extra="forbid"` sul corpo della richiesta.** Un `sessionId` scritto in camelCase
    sarebbe altrimenti ignorato in silenzio, e il cliente perderebbe la conversazione senza
    alcun errore. Meglio un 422 che nomina il campo.
  - **`DELETE` su una sessione inesistente restituisce 204, non 404.** L'intenzione del
    chiamante è che la conversazione non esista più, e non esiste. Un 404 lo costringerebbe a
    distinguere due casi che per lui sono lo stesso.
  - **Un gestore d'eccezioni generale restituisce il contratto, non un 500.** `ChatService`
    cattura già i guasti del provider (ADR-009), quindi arrivare qui significa che si è rotto
    qualcosa di più esterno. Il cliente riceve comunque quattro campi, `needs_human=true` e
    l'header di ripiego; l'operatore riceve il traceback nel log.
- **Il `lifespan` costruisce l'agente una volta**, perché caricare `multilingual-e5-base`
  richiede secondi: farlo per richiesta renderebbe l'API inutilizzabile. I test lo aggirano
  iniettando un servizio finto in `app.state` prima dell'avvio, quindi **nessuno dei sedici
  test dell'API chiama un modello**.
- **Verifica end-to-end**, con il server vero e i `curl` del README: `/health` risponde `ok`
  con data di business 2026-10-12; l'esempio della traccia risponde a **entrambe** le parti
  della domanda con `sources: ["guides/bulbi_autunnali.md"]` e `confidence: high`; il
  multi-turn risolve «quelli dell'ordine di prima» nei giacinti dell'ordine 1046, cioè la
  memoria di sessione funziona attraverso HTTP; `DELETE` dà 204 e un messaggio vuoto dà 422.
- **Osservazione che sopravvive alla fase 7**: alla domanda «posso piantare **adesso** i bulbi
  di tulipano?» con business date 12 ottobre, l'agente risponde «le consiglio di attendere
  qualche giorno». È la prudenza già registrata in ADR-053, che l'intervento sull'escalation
  non ha toccato — e non doveva: quell'intervento aveva un altro bersaglio. Resta il candidato
  naturale per un secondo intervento misurato, se se ne farà uno.

## ADR-075 — Il notebook di consegna è generato, non scritto a mano

- **Contesto**: `notebooks/greenthumb_delivery.ipynb` è il deliverable (SPEC §13). Un
  notebook modificato in posto accumula output obsoleti, metadati di esecuzione e diff
  illeggibili: il formato `.ipynb` è JSON con il codice annegato dentro, e una revisione
  seria di quel diff non è praticabile.
- **Decisione**: `scripts/build_notebook.py` genera il notebook; il contenuto vive in
  stringhe Python in un file che si legge e si rivede come codice. È la stessa scelta di
  ADR-069 per il report dell'evaluation, applicata a un artefatto più grande.
- **Conseguenza per il lint**: il file è in gran parte *contenuto* del notebook, prosa
  Markdown e celle di codice dentro stringhe. `E501` è disattivata **solo** per quel file,
  con un commento che spiega perché: riformattare la prosa a 100 colonne peggiorerebbe
  l'artefatto per soddisfare una regola sul sorgente che lo genera. Tutte le altre regole
  restano attive.
- **Eseguibile in due ambienti, per costruzione**: ogni cella che differisce fra Colab e
  locale si dirama su `IN_COLAB`. Su Colab clona il repository, installa da
  `requirements.txt` e legge i Secrets; in locale usa il checkout corrente. Non è una
  comodità: è **l'unico modo di popolare e verificare gli output prima della consegna**, e
  `scripts/build_notebook.py` più `nbclient` fanno esattamente questo.
- **Due difetti trovati eseguendolo, che una revisione a vista non avrebbe visto**:
  1. **le sezioni con chiamate al modello venivano saltate in locale.** Il notebook
     derivava `HAS_KEY` da `os.environ`, dove su Colab i Secrets arrivano — ma in locale la
     chiave sta nel `.env`, che `Settings` legge da sé e non esporta. Le tre sezioni più
     importanti (agente, memoria, API) non avevano output. Corretto leggendo la chiave
     attraverso `Settings` ed esportandola nell'ambiente quando non si è su Colab.
  2. **la sezione dell'agente scriveva nel registro di esercizio.** Il primo output salvato
     citava `ESC-0006`: eseguire il notebook accumulava ticket, quindi il numero mostrato
     cambiava a ogni esecuzione e chi lo eseguiva sporcava il proprio registro.
     `scripts/demo_tools.py` aveva già risolto lo stesso problema con un file temporaneo; la
     sezione 6 ora fa lo stesso e mostra sempre `ESC-0001`.
- **Tre firme sbagliate per memoria**, trovate dalla prima esecuzione: `search(k=...)`
  invece di `top_k`, `SearchHit.score` invece di `similarity`, `TurnEvidence(retrieval_used=...)`
  invece di `retrieval_ran`. È la regola 1 di `docs/CONVENTIONS.md` applicata al codice **del
  progetto stesso**: non fidarsi della memoria sulle firme vale anche per le API che si sono scritte.
- **Controllo di sicurezza**: gli output salvati sono stati scansionati per chiavi del
  provider (`sk-...`) prima del commit. Nessuna presente — ed è un controllo da rifare a ogni
  rigenerazione, perché un notebook con output salvati è un file che **contiene** ciò che ha
  stampato.
- **Limite dichiarato**: gli output committati provengono dall'esecuzione **locale**. La
  verifica su runtime Colab pulito richiede che i commit siano pubblicati su GitHub, perché
  la prima cella clona il repository: finché il push non avviene, su Colab il notebook
  clonerebbe una versione precedente. È l'ultimo passo di R10 e non è ancora fatto.

## ADR-076 — Anche `import litellm` carica il `.env`, e questo rende obbligatorio un Secret

- **Contesto**: scoperto verificando cosa serve davvero su Colab. Un controllo scritto per
  rispondere alla domanda «il notebook gira con il solo `OPENAI_API_KEY`?» ha dato la risposta
  sbagliata, e la causa è interessante.
- **Misura**:

  ```
  prima di importare litellm: GREENTHUMB_LLM_MODEL in os.environ -> False
  dopo  aver importato litellm: GREENTHUMB_LLM_MODEL in os.environ -> True
  ```

  `import litellm` chiama `load_dotenv()` come effetto collaterale, esattamente come
  `import deepeval` (ADR-025). È la **quarta** manifestazione dello stesso problema, dopo
  l'ambiente iniettato da DeepEval, il `.env` letto direttamente da `Settings` (ADR-044) e il
  valore dimenticato nel `.env` che vinceva sul default calibrato (ADR-043, ADR-072).
- **Perché mi ha ingannato**: un controllo che costruiva `Settings(_env_file=None)` **dopo**
  aver importato `greenthumb.agent` leggeva `llm_model = 'openrouter/openai/gpt-4.1-mini'`,
  cioè il valore del `.env`, pur avendo disabilitato la lettura del file. Lo stesso controllo
  senza quell'import legge `''`. Non era `Settings` a sbagliare: era il file già riversato
  nell'ambiente da un import fatto tre righe sopra.
- **Conseguenza concreta sulla consegna**: su Colab non esiste alcun `.env` da cui ripiegare,
  quindi `GREENTHUMB_LLM_MODEL` è un Secret **obbligatorio**, non opzionale. Il default in
  `config.py` è la stringa vuota di proposito — un modello indovinato è peggio di un errore —
  e `build_chat_model` solleva un `ValueError` che nomina il `.env` e i Secrets di Colab.
- **Decisione**: il notebook dichiara quali Secrets sono obbligatori e quale è opzionale,
  distingue i due casi nel messaggio che stampa quando uno manca, e deriva `HAS_KEY` da
  **entrambi** i valori richiesti invece che dalla sola chiave. In locale esporta
  nell'ambiente sia la chiave sia il modello letti da `Settings`.
- **Lezione generale**: in questo ecosistema l'import di una libreria è un'operazione con
  effetti collaterali sull'ambiente del processo. Qualunque verifica su «cosa serve davvero
  per far partire il sistema» va fatta in un processo dove quelle librerie **non** sono state
  importate, altrimenti misura la macchina di sviluppo invece dell'ambiente di consegna.
