# Registro delle decisioni architetturali

Formato: contesto → decisione → alternative scartate → conseguenze.
Questo file è la fonte primaria della relazione tecnica. Aggiungere una voce per ogni scelta non
ovvia, inclusi gli esiti degli spike della fase 0 e i numeri delle calibrazioni.

---

## ADR-001 — Sviluppo in repository locale, consegna via notebook Colab

- **Contesto**: la consegna è un link Colab; la traccia chiede anche un repository.
- **Decisione**: sviluppo in un repository Python con Claude Code; il notebook clona il repo e ne
  esegue le parti, contenendo la relazione.
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
  parte del materiale online è obsoleto — vale la regola 3 di CLAUDE.md. Si noti anche che
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
- **Conseguenze**: conferma la regola 3 di CLAUDE.md — quasi tutto il materiale online su RAGAS
  usa il percorso deprecato. Le firme esatte delle due metriche restano da verificare nello
  spike n.5 (fase 0, passo 4).

## ADR-021 — Soglie calibrate sulla distanza grezza di Chroma

- **Contesto**: SPEC §6 parla di "score" senza dire quale API usare, e CLAUDE.md avverte di
  distinguere distanza da similarità. Spike n.4, nessuna chiamata LLM.
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

- **Contesto**: CLAUDE.md avverte che senza i prefissi `query: ` / `passage: ` "la qualità del
  retrieval crolla in modo silenzioso". Lo spike n.4 ha misurato l'affermazione.
- **Misura** (4 passaggi in italiano, 3 query pertinenti, 2 fuori tema):

  | | hit@1 | peggior distanza pertinente | miglior distanza fuori tema | separazione |
  |---|---|---|---|---|
  | con prefissi | 3/3 | 0.1304 | 0.2285 | **+0.0981** |
  | senza prefissi | 3/3 | 0.1346 | 0.2260 | **+0.0914** |

- **Esito**: i prefissi aiutano, ma di poco — la separazione migliora di 0.0067, e `hit@1` è
  perfetto in entrambi i casi. **Su questo campione il "crollo" descritto non si riproduce.**
- **Decisione**: usare comunque i prefissi. Sono l'uso documentato del modello, non costano
  nulla, e l'effetto atteso cresce con corpus più grandi e negativi più difficili di questi.
- **Conseguenze**: l'avvertimento di CLAUDE.md va ridimensionato, non ignorato. Il campione è di
  soli 4 documenti con negativi banali (capitali del Giappone, router wifi): va **rimisurato in
  fase 2** sulla KB reale da 35 documenti, dove i distrattori sono altri documenti di giardinaggio
  e quindi molto più insidiosi. Onestà del dato: non è ancora una prova che i prefissi siano
  superflui, ma nemmeno una conferma che siano critici.
- **Nota di calibrazione**: le distanze pertinenti stanno in 0.087–0.135 e le fuori tema in
  0.226–0.272. La fascia è alta e stretta, come CLAUDE.md prevedeva: una soglia plausibile cade
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

- **Contesto**: CLAUDE.md avverte che gli score di e5 si concentrano in una fascia alta e
  stretta e vanno calibrati empiricamente. Misurato con `scripts/probe_retrieval.py` su 12 query
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
- **L'avvertimento di CLAUDE.md è confermato, e in forma severa**: la separazione è di appena
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
- Tabelle complete in `docs/retrieval_calibration.md`.

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
  praticamente identica. **Il «crollo silenzioso» descritto da CLAUDE.md non si verifica** su
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

<!-- Fase 0: aggiungere qui gli esiti degli spike (API verificate, strategia di structured output). -->
