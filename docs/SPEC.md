# Specifica tecnica

## 1. Requisiti d'esame e tracciabilità

Ogni requisito della consegna deve essere soddisfatto in un punto verificabile. Questa tabella
va mantenuta aggiornata: a fine progetto è la checklist di consegna.

| # | Requisito | Dove viene soddisfatto | Verificato |
|---|---|---|---|
| R1 | Agente ReAct con LangChain e LiteLLM | `src/greenthumb/agent.py` (§8) | ✅ `create_agent` + `ChatLiteLLM`; notebook §6 |
| R2 | ≥3 tool: RAG sul catalogo, stato ordine, escalation | `src/greenthumb/tools/` (§7) | ✅ tre tool, casi limite in `scripts/demo_tools.py`; notebook §5 |
| R3 | Memoria breve termine esplicita + lungo termine semantica | `memory.py` (§9), `retrieval.py` (§6) | ✅ summarization misurata (2/2 nell'eval); notebook §4 e §7 |
| R4 | Output JSON: `answer`, `confidence`, `sources`, `needs_human` | `schemas.py`, `response.py` (§5) | ✅ `schema validity` 100% su 50 turni; test sul contratto a 4 campi |
| R5 | KB 37 documenti + `orders.json` ≥24 ordini | `data/` (§4) | ✅ 37 documenti, 26 ordini, `make data` verde |
| R6 | Eval ≥15 conversazioni, ≥1 metrica RAGAS + ≥1 DeepEval, con commento | `eval/` (§10) | ✅ 20 conversazioni, 2 RAGAS + 3 DeepEval + 6 deterministiche, confronto prima/dopo |
| R7 | Deploy locale FastAPI con istruzioni di avvio | `api.py`, `README.md` (§11) | ✅ provato con server reale e i curl del README (ADR-074) |
| R8 | Relazione tecnica: architettura, memoria, analisi eval | notebook §10 + `docs/DECISIONS.md` (§13) | ✅ 75 ADR; relazione in sei sottosezioni |
| R9 | Naming inglese snake_case / CamelCase, docstring ovunque | tutto il codice, verificato da ruff | ✅ `make lint` pulito con regole `D`, `N`, `ANN` |
| R10 | Consegna come notebook Colab pubblico | `notebooks/greenthumb_delivery.ipynb` (§13) | ⏳ notebook eseguito con output salvati; **resta da pubblicare su Colab dopo il push** |

## 2. Stack

Versioni verificate come compatibili tra loro (risoluzione pip senza conflitti) il 2026-09-21.
Fissarle in `pyproject.toml`; aggiornarle solo con motivazione in DECISIONS.md.

| Pacchetto | Versione | Ruolo |
|---|---|---|
| Python | 3.11 o 3.12 | allineato al runtime Colab |
| langchain | 1.4.2 | `create_agent`, middleware |
| langchain-core | 1.6.3 | messaggi, tool, fake model per test |
| langgraph | 1.2.11 | checkpointer per la memoria di sessione |
| langchain-litellm | 0.7.2 | `ChatLiteLLM` |
| litellm | 1.102.0 | astrazione del provider LLM |
| langchain-chroma / chromadb | 1.1.0 / 1.5.9 | vector store persistente |
| langchain-text-splitters | 1.1.2 | chunking Markdown |
| langchain-huggingface | 1.2.2 | embedding locali |
| sentence-transformers | `>=5.2,<6` | backend embedding (vincolo di langchain-huggingface) |
| ragas | 0.4.3 | metriche RAG |
| deepeval | 4.2.3 | metriche risposta e conversazionali |
| fastapi / uvicorn | 0.141.1 / 0.53.0 | API |
| pydantic | 2.13.5 | schemi |
| python-frontmatter, pyyaml | latest | parsing KB |
| pytest, ruff | latest (dev) | test e lint |

Gestione ambiente: `uv`. Esportare anche `requirements.txt` (`uv export`) per l'installazione su Colab.

## 3. Struttura del repository

```
acattaneo_progetto3/
├── README.md                    # setup, avvio API, esempi curl
├── Makefile
├── pyproject.toml / uv.lock / requirements.txt
├── .env.example                 # mai .env
├── data/
│   ├── catalog.yaml             # fonte di verità dei prodotti (SKU, prezzi, categorie)
│   ├── kb/
│   │   ├── products/*.md
│   │   ├── guides/*.md
│   │   └── policies/*.md
│   └── orders.json              # generato da scripts/generate_orders.py (committato)
├── scripts/
│   ├── generate_orders.py       # deterministico, seed fisso
│   ├── validate_data.py         # controlli di coerenza KB ↔ catalogo ↔ ordini
│   ├── build_index.py
│   ├── probe_retrieval.py       # calibrazione soglie (fase 2)
│   ├── ablation_e5_prefixes.py  # ablazione sui prefissi e5 (ADR-046)
│   ├── demo_tools.py            # demo dei tre tool, senza LLM (fase 3)
│   └── demo_memory.py           # demo della summarization (fase 5)
├── src/greenthumb/
│   ├── config.py                # Settings (pydantic-settings o dataclass)
│   ├── clock.py                 # Clock protocol + FrozenClock / SystemClock
│   ├── schemas.py               # ChatResponse, modelli dei tool
│   ├── kb_loader.py             # lettura Markdown + frontmatter
│   ├── retrieval.py             # chunking, embedding, Chroma, search
│   ├── orders_repository.py     # accesso a orders.json
│   ├── escalations_repository.py # registro dei ticket (ADR-048)
│   ├── tools/
│   │   ├── knowledge_base_tool.py
│   │   ├── order_status_tool.py
│   │   └── escalation_tool.py
│   ├── prompts.py               # system prompt e prompt di summarization
│   ├── memory.py                # configurazione memoria breve termine
│   ├── agent.py                 # costruzione agente
│   ├── response.py              # assemblaggio deterministico di ChatResponse
│   ├── service.py               # chat(message, session_id) usata da API ed evaluation
│   └── api.py                   # FastAPI
├── eval/
│   ├── conversations.jsonl      # dataset (§10)
│   ├── runner.py                # replay conversazioni → trace
│   ├── metrics_ragas.py
│   ├── metrics_deepeval.py
│   ├── metrics_deterministic.py
│   └── results/                 # output versionati (json + summary.md)
├── notebooks/greenthumb_delivery.ipynb
├── tests/
└── docs/
    ├── CONVENTIONS.md            # convenzioni di codice e insidie delle librerie
    ├── SPEC.md
    ├── PLAN.md
    └── DECISIONS.md
```

## 4. Dati

### 4.1 Data simulata (business date)

Il sistema non usa la data reale ma una **data di business simulata**, configurabile
(`GREENTHUMB_TODAY`, default `2026-10-12`). Motivazione: ordini, domande stagionali e ground
truth dell'evaluation devono restare coerenti indipendentemente da quando il notebook viene
eseguito dal docente. Con la data reale, un ordine "in consegna domani" diventerebbe "consegnato
da un mese" e l'evaluation perderebbe validità. Il default autunnale rende rilevanti le domande
sui bulbi (esempio della traccia). `SystemClock` resta disponibile per l'uso reale.

### 4.2 Catalogo (`data/catalog.yaml`)

Fonte unica di verità dei prodotti. Da essa derivano le schede prodotto e gli ordini.
16 prodotti distribuiti sulle sei categorie della bio aziendale. Campi per prodotto: `sku`
(formato `GT-<CAT>-<NNN>`, es. `GT-BUL-001`), `name`, `short_description`, `category`,
`price_eur`, `perishable` (bool: sementi e bulbi sì), `season`, `kb_path` (con estensione,
ADR-006).

`short_description` e `season` sono aggiunte rispetto alla stesura iniziale (ADR-034).
`season` elenca le stagioni in cui il prodotto è rilevante — per bulbi e sementi la
finestra di messa a dimora o semina, per gli altri il periodo d'uso — con valori
identici a quelli restituiti da `clock.season_of()`; tutte e quattro significa
«tutto l'anno».

### 4.3 Knowledge base (37 documenti, Markdown con frontmatter)

| Cartella | N. | Contenuto |
|---|---|---|
| `products/` | 16 | una scheda per prodotto del catalogo |
| `guides/` | 14 | guide di coltivazione e cura: stagionali, per contesto di coltivazione (balcone, vaso, poca luce) e per problema (annaffiatura, ingiallimento, ristagni) |
| `policies/` | 7 | resi e rimborsi, spedizioni, prodotti deperibili, garanzia attrezzi, danni da trasporto, pagamenti, contatti e orari |
| **Totale** | **37** | (ADR-035) |

Deve esistere `guides/bulbi_autunnali.md` (citato nell'esempio della traccia).

Frontmatter obbligatorio:

```yaml
---
doc_id: guides/bulbi_autunnali.md   # = path relativo dentro data/kb/, CON estensione
title: Bulbi a fioritura primaverile: quando e come piantarli
doc_type: guide                      # product | guide | policy
category: bulbi                      # categoria merceologica o "generale"
season: [autunno]                    # opzionale, per le guide
related_skus: [GT-BUL-001, GT-BUL-002]
---
```

Regole di contenuto:
- Italiano, tono da e-commerce professionale, 250–700 parole per documento.
- **Non ripetitivi**: strutture diverse tra documenti dello stesso tipo; evitare template identici
  con parole sostituite (la traccia lo richiede esplicitamente).
- Informazioni agronomiche realistiche per il clima del Nord Italia.
- Fatti verificabili e specifici (dosi, periodi, tempi, soglie di policy): sono ciò su cui
  l'evaluation misura la faithfulness.
- Includere deliberatamente alcune informazioni che *solo* la KB contiene (es. "i bulbi non sono
  rimborsabili dopo 14 giorni dalla consegna"), così da poter verificare che l'agente usi il
  retrieval invece della conoscenza generale del modello.
- Coerenza incrociata: prezzi, SKU e nomi coincidono con `catalog.yaml`; le policy non si
  contraddicono tra loro. `validate_data.py` lo verifica.

### 4.4 Ordini (`data/orders.json`)

Generati da `scripts/generate_orders.py` con seed fisso, relativi alla business date. Il file
generato viene committato (è un deliverable).

```json
{
  "order_id": "1042",
  "customer_name": "Giulia Ferri",
  "customer_email": "giulia.ferri@example.com",
  "created_at": "2026-10-08",
  "status": "shipped",
  "items": [{"sku": "GT-BUL-001", "name": "...", "quantity": 2, "unit_price_eur": 7.90}],
  "total_eur": 15.80,
  "carrier": "BRT",
  "tracking_code": "BRT00012345",
  "estimated_delivery": "2026-10-13",
  "delivered_at": null,
  "return": null
}
```

- ≥24 ordini, ID numerici come stringa. **L'ordine `1042` deve esistere**, `shipped`, con
  consegna stimata = business date + 1 giorno (esempio della traccia).
- Stati: `processing`, `shipped`, `delivered`, `return_requested`, `returned`, `refunded`,
  `cancelled`. Ogni stato ha almeno 2 ordini.
- Casi limite intenzionali: consegna in ritardo, ordine multi-articolo, reso di prodotto
  deperibile fuori termine, rimborso parziale, ordine di un bulbo appena consegnato.
- Oggetto `return` per gli stati di reso/rimborso: `requested_at`, `reason`, `refund_amount_eur`,
  `refunded_at`.

## 5. Contratto di risposta

```python
class ChatResponse(BaseModel):
    answer: str
    confidence: Literal["high", "medium", "low"]
    sources: list[str]  # doc_id, es. "guides/bulbi_autunnali.md"
    needs_human: bool
```

Il corpo della risposta API contiene **esattamente** questi quattro campi, come nell'esempio
della traccia. La generazione è divisa in due livelli:

**Livello LLM** (structured output dell'agente): `answer`, `proposed_confidence`, `cited_sources`.

**Livello deterministico** (`response.py`), che produce la `ChatResponse` finale:
- `sources` = `cited_sources` ∩ documenti effettivamente restituiti dal retrieval nel turno
  (con score sopra soglia). Se l'LLM non cita nulla ma il retrieval ha prodotto risultati usati,
  fallback sui documenti recuperati sopra soglia. Solo documenti della KB: i dati ordine non sono
  una "source" (coerente con l'esempio della traccia).
- `needs_human` = `true` sse la sessione ha almeno un ticket di escalation aperto, cioè
  `escalate_to_human` è stato invocato con successo in questo turno **o in un turno
  precedente della stessa sessione**. Resta deterministico: deriva dal registro delle
  escalation della sessione, non da un giudizio dell'LLM. (ADR-008)
- `confidence` = minimo tra `proposed_confidence` e il cap deterministico:
  - domanda risolta solo con dati ordine (fonte strutturata) → nessun cap;
  - retrieval usato, miglior score ≥ soglia alta → cap `high`;
  - retrieval usato, miglior score tra soglia bassa e alta → cap `medium`;
  - retrieval senza risultati sopra soglia → cap `low`;
  - nessun tool invocato → cap `medium`: un rifiuto fuori ambito, una domanda di chiarimento e
    una risposta non ancorata alla KB hanno la stessa impronta osservabile, e il cap si decide
    sul peggiore dei tre (ADR-058).
  L'escalation **non** influisce sulla confidence: `confidence` qualifica la risposta,
  `needs_human` ne governa l'instradamento. (ADR-007)
  Le soglie vengono calibrate in fase 2 e salvate in config.

I tool restituiscono i propri metadati come *artifact* (`response_format="content_and_artifact"`
in LangChain), così `response.py` può leggerli dai `ToolMessage` del turno senza parsing di testo.
Verificare questa API sulla versione installata.

Strategia di structured output: verificare in fase 0 se il modello scelto supporta
`response_format` nativo via LiteLLM (ProviderStrategy); altrimenti ToolStrategy. Documentare in
DECISIONS.md. Fallback robusto: se il parsing fallisce, risposta di cortesia con
`confidence="low"`, `needs_human=true`, e log dell'errore. **Mai** un 500 verso il cliente per un
errore di formato.

## 6. Memoria a lungo termine semantica (RAG)

- **Loader**: legge i Markdown, separa frontmatter e corpo, propaga i metadati su ogni chunk.
- **Chunking**: `MarkdownHeaderTextSplitter` su `#`/`##`/`###`, poi
  `RecursiveCharacterTextSplitter` solo per sezioni oltre ~1200 caratteri (overlap ~150).
  Ogni chunk viene prefissato con il titolo del documento e il percorso di heading, perché un
  chunk tipo "Dosi: 30 g/m²" è inutile se non dice di quale prodotto parla.
  Motivazione: documenti brevi e ben strutturati → unità semantiche naturali; il chunking a
  dimensione fissa spezzerebbe tabelle di dosaggio e paragrafi di policy.
- **Embedding**: `intfloat/multilingual-e5-base`, locale, con normalizzazione; prefissi
  `query:` / `passage:` obbligatori.
- **Store**: Chroma persistente in `vector_store/` (non versionato, ricostruito da `make index`),
  metrica coseno.
- **Ricerca**: top-k = 4, filtro opzionale per `doc_type`. Soglia minima di rilevanza calibrata
  (fase 2). Sotto soglia → esito esplicito "nessun documento rilevante".
- **Re-ranking**: fuori dal nucleo. Opzionale in fase 7 come esperimento misurato (con e senza),
  solo se il tempo lo permette.

## 7. Tool

Ogni tool: nome parlante, descrizione scritta per il modello (quando usarlo e quando **non**
usarlo), input Pydantic, output strutturato, casi limite gestiti senza eccezioni verso l'agente.

### `search_knowledge_base`
- Input: `query: str` (riformulata in modo autonomo, non la frase del cliente se ambigua),
  `doc_type: Literal["product","guide","policy"] | None`.
- Output content: elenco testuale dei chunk con titolo e `doc_id`. Artifact: lista di
  `{doc_id, score, chunk_id, text}`. Il testo del chunk è duplicato nell'artifact perché le
  metriche RAGAS misurano la faithfulness contro i contesti recuperati, e ricavarli dal
  contenuto formattato per il modello sarebbe fragile (ADR-059).
- Casi limite: nessun risultato sopra soglia → messaggio esplicito che invita a non inventare e a
  valutare l'escalation; query vuota → errore di validazione leggibile.

### `get_order_status`
- Input: `order_id: str` (normalizzato: rimuovere `#`, spazi, prefissi tipo "ordine").
- Output: stato, articoli, date, tracking, info reso. Le date sono restituite sia in ISO sia in
  forma relativa alla business date ("domani", "3 giorni fa"), calcolata dal codice, così l'LLM
  non deve fare aritmetica sulle date.
- Casi limite: ordine inesistente → `{"found": false}` con suggerimento di verificare il numero;
  ID malformato → idem. Mai esporre dati di altri ordini.
- Nota privacy (da citare nella relazione): in produzione servirebbe verificare l'identità del
  cliente (email dell'ordine) prima di rivelare dettagli. Qui non lo implementiamo ma lo
  documentiamo come limite noto.

### `escalate_to_human`
- Input: `reason: Literal[...]` (vedi §8), `summary: str` (sintesi per l'operatore),
  `order_id: str | None`.
- Effetto: append di un ticket in `escalations.jsonl` (non versionato), con timestamp dalla
  business date, `ticket_id` progressivo (`ESC-0001`) e session_id.
- Output: `ticket_id` e testo da comunicare al cliente (tempi di presa in carico da policy
  contatti).
- Idempotenza: una sola escalation per sessione e motivo; chiamate ripetute restituiscono il
  ticket esistente.

## 8. Agente

- `create_agent` con `ChatLiteLLM` (modello da config, temperature bassa), i tre tool,
  structured output (§5), memoria (§9), checkpointer con `thread_id = session_id`.
- **System prompt** (`prompts.py`), sezioni:
  1. Ruolo e tono (assistente GreenThumb, italiano, cordiale e conciso).
  2. Business date iniettata dinamicamente a ogni invocazione, con stagione corrente.
  3. Regole di grounding: informazioni su prodotti, policy e consigli agronomici **solo** dalla
     KB; se il retrieval non trova nulla, dirlo, non inventare. Dati ordine solo dal tool ordini.
  4. Orchestrazione: una domanda può richiedere più tool (es. ordine + guida); scomporla.
  5. Chiarimenti: se la richiesta è ambigua (es. "il mio ordine" senza numero), chiedere prima di
     agire.
  6. Criteri di escalation (sotto).
  7. Formato: rispondere a tutte le parti della domanda; niente dettagli interni (tool, score).
- **Criteri di escalation** (enum `reason`):
  - `customer_request` – il cliente chiede esplicitamente un operatore;
  - `refund_exception` – rimborso o reso fuori dai termini di policy, o richiesta di eccezione;
  - `damaged_or_wrong_item` – merce danneggiata, errata o mancante;
  - `complaint` – reclamo o cliente chiaramente insoddisfatto;
  - `order_not_found` – ordine non trovato dopo un secondo tentativo con numero confermato;
  - `no_knowledge` – domanda pertinente ma nessun documento rilevante;
  - `safety` – ingestione di prodotti, tossicità per persone o animali, reazioni allergiche.
  Fuori scope (es. domande non legate al giardinaggio): **non** è escalation, rifiuto cortese.
- Protezione dai loop: limite di iterazioni del ciclo ReAct (8, vedi ADR-012); al superamento, risposta di
  fallback con escalation.

## 9. Memoria a breve termine

- **Strategia: summarization** (non trimming), tramite il middleware di summarization di
  LangChain 1.x (verificare nome e parametri sulla versione installata).
- Parametri calibrati in fase 5 e ricalibrati in fase 7 (ADR-056, ADR-072): trigger a
  **6000 token**, ultimi 6 messaggi
  mantenuti integri. Attenzione: la soglia si confronta con il `total_tokens` che il provider
  riporta per l'intera richiesta, **system prompt e schemi dei tool inclusi**, non con i soli
  token della conversazione. Il pavimento misurato e' ~2583 token alla prima chiamata, quindi
  il valore inizialmente previsto (2500) avrebbe fatto scattare la summarization a ogni
  chiamata. Un validatore in `config.py` rifiuta valori sotto 3000.
- Prompt di summarization personalizzato che **deve** preservare: numeri d'ordine citati,
  prodotti/SKU discussi, escalation aperte con ticket_id, preferenze o vincoli espressi dal
  cliente (es. "coltivo sul balcone").
- Motivazione da riportare: nel customer care le entità citate all'inizio (numero d'ordine)
  vengono riprese molti turni dopo ("e quello di prima?"); il trimming le perderebbe. Costo: una
  chiamata LLM aggiuntiva quando scatta la soglia. Alternativa scartata: trimming + estrazione
  entità in stato strutturato (più deterministico, ma più codice; citarla come possibile
  evoluzione).
- Sessioni: checkpointer in memoria (`InMemorySaver`), una conversazione per `session_id`.
  Limite noto: le sessioni si perdono al riavvio del server (in produzione: checkpointer
  persistente, es. Postgres/SQLite).
- Test dedicato: conversazione lunga che supera la soglia; verificare che il numero d'ordine del
  turno 1 sia ancora utilizzabile dopo la summarization.

## 10. Evaluation

### 10.1 Dataset (`eval/conversations.jsonl`)

20 conversazioni (requisito: ≥15), una per riga:

```json
{
  "conversation_id": "conv_07",
  "category": "multi_tool",
  "turns": [
    {
      "user": "Quando arriva l'ordine 1042? Posso piantare adesso i bulbi di tulipano?",
      "reference_answer": "L'ordine 1042 arriva domani. ... ",
      "expected_sources": ["guides/bulbi_autunnali.md"],
      "expected_tools": ["get_order_status", "search_knowledge_base"],
      "expected_needs_human": false
    }
  ]
}
```

Distribuzione per `category`:

| Categoria | N. | Cosa verifica |
|---|---|---|
| `product_info` | 3 | retrieval su schede prodotto |
| `agronomic_advice` | 3 | retrieval su guide, dipendenza dalla stagione |
| `order_status` | 2 | tool ordini, date relative |
| `returns_policy` | 2 | policy, casi entro/fuori termine |
| `multi_tool` | 3 | orchestrazione (incluso l'esempio della traccia) |
| `escalation` | 3 | criteri di escalation, copertura dell'enum `reason` |
| `memory` | 2 | multi-turn lungo, riferimenti a turni precedenti, oltre la soglia di summarization |
| `edge_cases` | 2 | ordine inesistente (1° tentativo → `needs_human=false`, ADR-011),
domanda fuori scope, richiesta ambigua |

Almeno 6 conversazioni multi-turn. Le reference answer si basano solo sul contenuto della KB e
degli ordini (non su conoscenza generale).

### 10.2 Runner

`eval/runner.py` riproduce ogni conversazione con `FrozenClock` e una sessione nuova, e salva
per ogni turno: risposta finale, `ChatResponse`, contesti recuperati (testo dei chunk), tool
invocati. Output in `eval/results/traces.jsonl`. Le metriche leggono le trace: si possono
ricalcolare senza rieseguire l'agente (risparmio di costo).

### 10.3 Metriche

| Libreria | Metrica | Cosa misura | Su quali turni |
|---|---|---|---|
| RAGAS | Faithfulness | la risposta è supportata dai contesti recuperati | turni con retrieval |
| RAGAS | Context precision (with reference) | qualità del ranking del retrieval | turni con retrieval |
| DeepEval | Answer relevancy | la risposta risponde alla domanda | tutti |
| DeepEval | GEval "escalation correctness" | escalation giustificata e comunicata bene | escalation + edge case |
| DeepEval | Knowledge retention (conversazionale) | la memoria a breve termine regge | conversazioni `memory` |
| Deterministica | Accuratezza `needs_human` | flag vs atteso | tutti |
| Deterministica | Tool selection accuracy | tool invocati vs attesi | tutti |
| Deterministica | Source recall | `expected_sources` presenti in `sources` | turni con fonti attese |
| Deterministica | Schema validity | risposte che rispettano `ChatResponse` | tutti |

Il minimo richiesto è una metrica RAGAS e una DeepEval; le altre rafforzano l'analisi. Verificare
nomi e firme delle metriche sulle versioni installate. Il modello giudice è configurabile
(`EVAL_MODEL`); se diverso dal modello dell'agente, riduce il bias di auto-valutazione (da
discutere nella relazione).

### 10.4 Report dei risultati

`eval/results/summary.md` con: tabella aggregata per metrica e per categoria, i 3 casi peggiori
analizzati (causa: retrieval, prompt, tool, memoria?), e almeno un intervento correttivo misurato
(prima/dopo). Una valutazione con tutti i punteggi al massimo è meno credibile di una che mostra
dove il sistema cede.

## 11. API (FastAPI)

- `POST /chat` — body `{"message": str, "session_id": str | null}`. Risposta: `ChatResponse`
  (esattamente i 4 campi). Il `session_id` (generato se assente) viene restituito nell'header
  `X-Session-Id`, per non alterare il contratto JSON della traccia.
- `GET /health` — stato di vector store, config modello (senza segreti), business date.
- `DELETE /sessions/{session_id}` — reset di una conversazione.
- Agente e vector store inizializzati una sola volta nel `lifespan`.
- Errori: validazione input → 422; errore LLM/provider → risposta `ChatResponse` di fallback con
  `needs_human=true` e status 200, più log, più header `X-Fallback: true` perché
  l'indisponibilità del provider resti osservabile senza alterare il JSON (ADR-009).
  Messaggi vuoti o oltre 2000 caratteri → 422.
- README: comandi di avvio, esempio `curl` con l'esempio della traccia, esempio multi-turn con
  `session_id`.

## 12. Configurazione

`src/greenthumb/config.py`, unica fonte dei parametri. Tutte le variabili di progetto usano
il prefisso `GREENTHUMB_` per non collidere con l'ambiente condiviso di Colab (ADR-013);
fanno eccezione le chiavi dei provider, il cui nome è imposto dall'SDK. Variabili
(vedi `.env.example`): `GREENTHUMB_LLM_MODEL`, `GREENTHUMB_EVAL_MODEL`, chiave provider
`OPENAI_API_KEY`, `GREENTHUMB_TODAY`, `GREENTHUMB_EMBEDDING_MODEL`,
`GREENTHUMB_RETRIEVAL_TOP_K`, `GREENTHUMB_RETRIEVAL_SCORE_LOW`,
`GREENTHUMB_RETRIEVAL_SCORE_HIGH`, `GREENTHUMB_SUMMARY_TRIGGER_TOKENS`,
`GREENTHUMB_SUMMARY_KEEP_MESSAGES`, `GREENTHUMB_AGENT_MAX_ITERATIONS`,
`GREENTHUMB_MAX_OUTPUT_TOKENS` (ADR-031).
`GREENTHUMB_EVAL_MODEL` è validato in modo **pigro**, solo quando l'evaluation viene
effettivamente eseguita, così il notebook gira con il solo segreto dell'agente (ADR-010). Su Colab i valori arrivano dai Secrets e
vengono esportati come variabili d'ambiente prima dell'import del pacchetto.

## 13. Notebook di consegna e relazione

`notebooks/greenthumb_delivery.ipynb`, eseguibile con "Esegui tutto" su runtime pulito:

1. Introduzione e mappa dei requisiti (tabella §1).
2. Setup: clone del repo, `pip install -r requirements.txt`, Secrets, verifica ambiente.
3. Dati: statistiche della KB e degli ordini, esempio di documento.
4. Indicizzazione e prova del retrieval (con score).
5. Demo dei tool, inclusi i casi limite.
6. Demo dell'agente: esempio della traccia, multi-turn, escalation.
7. Memoria: dimostrazione della summarization.
8. Evaluation: caricamento dei risultati salvati + opzione per rieseguirla; tabelle e commento.
9. API: avvio di uvicorn in thread, chiamate `POST /chat` reali; istruzioni per l'avvio locale.
10. Relazione: scelte architetturali (da DECISIONS.md), strategia di memoria, analisi dei
    risultati, limiti e sviluppi futuri.

Gli output delle celle vengono salvati nel notebook consegnato: chi valuta deve poter leggere
tutto senza rieseguire (e senza spendere chiamate LLM).

## 14. Fuori scope

Autenticazione dei clienti, persistenza delle sessioni, interfaccia grafica, deploy cloud,
integrazioni reali (e-commerce, ticketing), streaming delle risposte. Vanno citati nella
relazione come sviluppi futuri, non implementati.
