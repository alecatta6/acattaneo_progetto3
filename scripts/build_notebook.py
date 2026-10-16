"""Build ``notebooks/greenthumb_delivery.ipynb``.

The notebook is the deliverable (SPEC section 13), and it is generated rather than written
by hand for the same reason the evaluation report is (ADR-069): a notebook edited in place
accumulates stale outputs and untracked diffs, while a generator keeps its structure
reviewable in a diff and reproducible from scratch.

The notebook must run with "Run all" on a clean Colab runtime **and** here, so that its
outputs can be populated and checked before delivery. Every cell that differs between the
two environments branches on ``IN_COLAB``.

Run with: uv run python scripts/build_notebook.py
"""

from __future__ import annotations

import pathlib

import nbformat

NOTEBOOK_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "notebooks" / "greenthumb_delivery.ipynb"
)
REPO_URL = "https://github.com/alecatta6/acattaneo_progetto3.git"

cells: list[nbformat.NotebookNode] = []


def md(source: str) -> None:
    """Append a Markdown cell.

    Args:
        source: The cell's Markdown, without trailing newline handling.
    """
    cells.append(nbformat.v4.new_markdown_cell(source.strip("\n")))


def code(source: str) -> None:
    """Append a code cell.

    Args:
        source: The cell's Python.
    """
    cells.append(nbformat.v4.new_code_cell(source.strip("\n")))


# =====================================================================================
# 1. Introduzione e mappa dei requisiti
# =====================================================================================

md(
    """
# GreenThumb Customer Care Agent

Agente conversazionale **ReAct** per il customer care di primo livello di *GreenThumb
Marketplace*, un e-commerce fittizio di articoli per il giardinaggio. L'agente risponde a
domande su prodotti, coltivazione, ordini e resi attingendo a una knowledge base curata, e
riconosce quando serve un operatore umano.

Progetto d'esame del Master in AI Solution Architecture — Alessandro Cattaneo.

Questo notebook è l'involucro di consegna: clona il repository, ne esegue le parti
significative e contiene la relazione tecnica. Lo sviluppo è avvenuto nel repository, dove
stanno il codice, i test e il registro delle decisioni architetturali.

---

## Come leggere questo notebook

Gli output delle celle sono **salvati**: si può leggere tutto senza rieseguire nulla e
senza spendere chiamate al modello. Chi vuole rieseguire ha bisogno di un solo segreto,
`OPENAI_API_KEY`, nei Secrets di Colab.

Le sezioni 6, 7 e 9 effettuano chiamate reali al modello; le altre no. L'evaluation
completa **non** viene rieseguita: il notebook carica i risultati già salvati nel
repository, e la cella per rilanciarla è presente ma commentata, perché costa circa 300
chiamate.

## Mappa dei requisiti

| # | Requisito | Dove è soddisfatto | Sezione di questo notebook |
|---|---|---|---|
| R1 | Agente ReAct con LangChain e LiteLLM | `src/greenthumb/agent.py` | 6 |
| R2 | ≥3 tool: RAG, stato ordine, escalation | `src/greenthumb/tools/` | 5 |
| R3 | Memoria breve termine + lungo termine semantica | `memory.py`, `retrieval.py` | 4, 7 |
| R4 | Output JSON a 4 campi | `schemas.py`, `response.py` | 6, 9 |
| R5 | KB 37 documenti + 26 ordini | `data/` | 3 |
| R6 | Eval ≥15 conversazioni, RAGAS + DeepEval | `eval/` | 8 |
| R7 | Deploy locale FastAPI | `api.py`, `README.md` | 9 |
| R8 | Relazione tecnica | questo notebook + `docs/DECISIONS.md` | 10 |
| R9 | Naming inglese, docstring, lint | tutto il codice | 2 |
| R10 | Consegna come notebook Colab pubblico | questo file | — |
"""
)

# =====================================================================================
# 2. Setup
# =====================================================================================

md(
    """
---
## 2. Setup

Una sola cella fa tutto: rileva l'ambiente, clona il repository su Colab, installa le
dipendenze e legge il segreto dai Secrets. In locale non clona nulla e usa il checkout
corrente, così lo stesso notebook è eseguibile in entrambi gli ambienti — che è anche il
modo in cui i suoi output sono stati prodotti e verificati prima della consegna.
"""
)

code(
    f"""
import os
import pathlib
import subprocess
import sys

IN_COLAB = "google.colab" in sys.modules
REPO_URL = "{REPO_URL}"
REPO_DIR = pathlib.Path("/content/acattaneo_progetto3") if IN_COLAB else pathlib.Path.cwd()

if IN_COLAB:
    if not REPO_DIR.exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)], check=True)
    os.chdir(REPO_DIR)
    print("Installazione delle dipendenze (qualche minuto)...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True
    )
    from google.colab import userdata  # noqa: PLC0415 - disponibile solo su Colab

    # I nomi dei Secrets coincidono con quelli del .env (ADR-013).
    for name in ("OPENAI_API_KEY", "GREENTHUMB_LLM_MODEL", "GREENTHUMB_EVAL_MODEL"):
        try:
            os.environ[name] = userdata.get(name)
        except Exception:
            print(f"Secret {{name}} non impostato: le celle che lo usano verranno saltate.")
else:
    # In locale si risale alla radice del repository, così il notebook funziona anche se
    # Jupyter viene avviato da notebooks/.
    while not (REPO_DIR / "pyproject.toml").exists() and REPO_DIR != REPO_DIR.parent:
        REPO_DIR = REPO_DIR.parent
    os.chdir(REPO_DIR)

sys.path.insert(0, str(REPO_DIR / "src"))
sys.path.insert(0, str(REPO_DIR))

if not IN_COLAB:
    # In locale la chiave sta nel .env, che Settings legge da se'. La esportiamo
    # nell'ambiente perche' i sottoprocessi e le librerie che leggono os.environ la
    # trovino: su Colab il percorso e' l'opposto, dai Secrets all'ambiente.
    from greenthumb.config import get_settings  # noqa: PLC0415

    _key = get_settings().openai_api_key
    if _key is not None:
        os.environ.setdefault("OPENAI_API_KEY", _key.get_secret_value())

HAS_KEY = bool(os.environ.get("OPENAI_API_KEY"))
print(f"Ambiente   : {{'Colab' if IN_COLAB else 'locale'}}")
print(f"Repository : {{REPO_DIR}}")
print(f"Python     : {{sys.version.split()[0]}}")
print(f"Chiave LLM : {{'presente' if HAS_KEY else 'ASSENTE — le sezioni 6, 7 e 9 verranno saltate'}}")
"""
)

md(
    """
### Verifica dell'ambiente

La configurazione passa tutta da `src/greenthumb/config.py`: nessun modulo legge
`os.environ` da sé, e tutte le variabili di progetto hanno prefisso `GREENTHUMB_` per non
collidere con l'ambiente condiviso di Colab (ADR-013). La **data di business è simulata**
(12 ottobre 2026) perché ordini, domande stagionali e ground truth dell'evaluation devono
restare coerenti indipendentemente da quando il notebook viene eseguito (ADR-003).
"""
)

code(
    """
from greenthumb.clock import season_of
from greenthumb.config import get_settings

settings = get_settings()
today = settings.clock().today()

print(f"Data di business : {today.isoformat()}  (stagione: {season_of(today)})")
print(f"Modello agente   : {settings.llm_model or '(non configurato)'}")
print(f"Modello giudice  : {settings.eval_model or '(non configurato)'}")
print(f"Embedding        : {settings.embedding_model}")
print(f"Soglie retrieval : low={settings.retrieval_score_low}  high={settings.retrieval_score_high}")
print(f"Summarization    : trigger {settings.summary_trigger_tokens} token, keep {settings.summary_keep_messages} messaggi")
print(f"Max iterazioni   : {settings.agent_max_iterations}   Max output: {settings.max_output_tokens} token")
"""
)

# =====================================================================================
# 3. Dati
# =====================================================================================

md(
    """
---
## 3. Dati

Tre fonti, con una gerarchia precisa: `data/catalog.yaml` è la **fonte unica di verità** dei
prodotti, da cui derivano le schede della knowledge base e gli ordini. Gli ordini sono
generati da codice con seed fisso (ADR-036), così due esecuzioni producono un file identico
byte per byte, e `scripts/validate_data.py` verifica la coerenza incrociata — SKU esistenti,
prezzi allineati, ogni stato coperto, l'ordine 1042 della traccia conforme.

Il validatore è testato **sui dati rotti**: i test corrompono di proposito SKU, stagioni,
totali e date e verificano che ciascuna corruzione venga segnalata (ADR-037). Un validatore
che passa sempre è indistinguibile dall'assenza di validatore.
"""
)

code(
    """
import collections
import json

import yaml

from greenthumb.kb_loader import load_knowledge_base
from greenthumb.orders_repository import OrdersRepository

catalog = yaml.safe_load((settings.data_dir / "catalog.yaml").read_text(encoding="utf-8"))["products"]
documents = load_knowledge_base(settings.kb_dir)
orders = OrdersRepository.from_file(settings.orders_path)
raw_orders = json.loads(settings.orders_path.read_text(encoding="utf-8"))

by_type = collections.Counter(doc.doc_type for doc in documents)
by_status = collections.Counter(order["status"] for order in raw_orders)
words = [len(doc.body.split()) for doc in documents]

print(f"Catalogo        : {len(catalog)} prodotti in {len({p['category'] for p in catalog})} categorie")
print(f"Knowledge base  : {len(documents)} documenti  ->  " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())))
print(f"Lunghezza doc.  : min {min(words)}, media {sum(words) // len(words)}, max {max(words)} parole")
print(f"Ordini          : {len(orders)}")
print("Stati ordine    : " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())))
print()
print("Rilevanza stagionale alla data di business:")
relevant = [p for p in catalog if season_of(today) in p["season"]]
print(f"  {len(relevant)} prodotti su {len(catalog)} sono di stagione in {season_of(today)}")
"""
)

md(
    """
Un documento di esempio. Il frontmatter è obbligatorio e il `doc_id` coincide sempre con il
percorso relativo **con estensione**: la stessa stringa compare nei metadati dei chunk, nel
campo `sources` della risposta e in `expected_sources` del dataset di evaluation, così non
esiste alcuna conversione da sbagliare in silenzio (ADR-006).
"""
)

code(
    """
example = next(doc for doc in documents if doc.doc_id == "guides/bulbi_autunnali.md")
print(f"doc_id   : {example.doc_id}")
print(f"title    : {example.title}")
print(f"doc_type : {example.doc_type}   category: {example.category}")
print(f"metadata : {example.metadata}")
print()
print(example.body[:700].rstrip() + "\\n[...]")
"""
)

md(
    """
L'ordine **1042** è quello dell'esempio della traccia: spedito, con consegna stimata al
giorno successivo alla data di business. Le date vengono restituite dal tool anche in forma
relativa, calcolata dal codice, così il modello non deve fare aritmetica sui calendari.
"""
)

code(
    """
order = orders.get("1042")
print(f"Ordine {order.order_id} — {order.customer_name}")
print(f"  stato            : {order.status}")
print(f"  creato il        : {order.created_at}")
print(f"  consegna stimata : {order.estimated_delivery}  (oggi è {today})")
print(f"  corriere         : {order.carrier}  tracking {order.tracking_code}")
print(f"  totale           : {order.total_eur:.2f} EUR")
for item in order.items:
    print(f"  - {item.quantity} x {item.name}  ({item.sku}, {item.unit_price_eur:.2f} EUR)")
print(f"  contiene deperibili: {order.has_perishable_items}")
"""
)

# =====================================================================================
# 4. Indicizzazione e retrieval
# =====================================================================================

md(
    """
---
## 4. Indicizzazione e retrieval — la memoria a lungo termine

Il vector store non è versionato: viene ricostruito da `make index`. La cella seguente lo
costruisce se manca, scaricando `intfloat/multilingual-e5-base` (circa 1,1 GB la prima
volta su Colab).

Tre scelte vanno dichiarate perché determinano la qualità di tutto il resto:

- **Chunking guidato dagli heading**, non dalla dimensione: i documenti sono brevi e ben
  strutturati, quindi le sezioni sono già unità semantiche. Un chunking a dimensione fissa
  spezzerebbe tabelle di dosaggio e paragrafi di policy. Ogni chunk è prefissato con titolo
  e percorso degli heading, perché un chunk che dice «Dose: 30 g/m²» è inutile se non dice
  di quale prodotto parli — e a catalogo ci sono quattro fertilizzanti (ADR-042, ADR-045).
- **Score come similarità, con formula nostra**: si interroga con
  `similarity_search_with_score`, che restituisce una distanza coseno, e si converte con
  `similarity = 1 − distanza`. L'alternativa — l'API che restituisce già una «relevance» —
  oggi darebbe gli stessi numeri, ma la sua normalizzazione è interna alla libreria e un
  aggiornamento potrebbe spostare in silenzio soglie calibrate con cura (ADR-021).
- **Prefissi e5 `query:` / `passage:`** applicati dentro `E5Embeddings`, così nessun
  chiamante può dimenticarli.
"""
)

code(
    """
from greenthumb.retrieval import chunk_knowledge_base, open_index, search

if not settings.vector_store_dir.exists() or not any(settings.vector_store_dir.iterdir()):
    print("Vector store assente: lo costruisco...")
    subprocess.run([sys.executable, "scripts/build_index.py"], check=True)

chunks = chunk_knowledge_base(documents)
lengths = [len(chunk.page_content) for chunk in chunks]
print(f"{len(documents)} documenti -> {len(chunks)} chunk ({len(chunks) / len(documents):.1f} per documento)")
print(f"Caratteri per chunk: min {min(lengths)}, media {sum(lengths) // len(lengths)}, max {max(lengths)}")
print()
print("Esempio di chunk, come lo legge il modello:")
print("-" * 92)
print(chunks[0].page_content[:420].rstrip())
print("-" * 92)
print(f"metadata: {chunks[0].metadata}")
"""
)

md(
    """
### Le soglie sono calibrate, non indovinate

`scripts/probe_retrieval.py` misura 12 query pertinenti e 8 fuori tema, tutte formulate
**senza riusare le frasi dei documenti**: usare le parole del documento gonfierebbe gli
score e calibrerebbe su una situazione irreale. Risultato: **hit@1 = 12/12, hit@4 = 12/12**.

| Gruppo | min | media | max |
|---|---|---|---|
| Pertinenti | 0.8195 | 0.8626 | 0.8873 |
| Fuori tema | 0.7346 | 0.7844 | 0.8063 |

Da qui `LOW = 0.813` (punto medio fra i due gruppi) e `HIGH = 0.863` (mediana dei
pertinenti). **La separazione è di appena +0.0132**, quindi la soglia non è un confine
affidabile e non va trattata come tale: è uno dei *tre* presidi contro le risposte fuori
ambito, insieme al rifiuto istruito nel system prompt e al cap sulla `confidence` (ADR-040).

La cella mostra il comportamento su una query pertinente e su una fuori tema. Si noti che
il motore **restituisce sempre qualcosa**: è la soglia, non il motore, a dover dichiarare
che nessun documento è rilevante.
"""
)

code(
    """
index = open_index(settings.vector_store_dir, settings.embedding_model)

for query in ("quando si piantano i bulbi di tulipano", "qual è la capitale del Giappone"):
    hits = search(index, query, top_k=settings.retrieval_top_k)
    print(f"Query: {query!r}")
    for hit in hits:
        above = hit.similarity >= settings.retrieval_score_low
        print(f"   {hit.similarity:.4f}  {'sopra soglia' if above else 'SOTTO soglia':12s}  {hit.doc_id}")
    print()
"""
)

# =====================================================================================
# 5. Demo dei tool
# =====================================================================================

md(
    """
---
## 5. I tre tool, casi limite compresi

Nessuna chiamata al modello in questa sezione: i tool sono invocabili singolarmente, ed è
così che sono stati sviluppati e testati. Lo script è lo stesso che serviva da Definition of
Done della fase 3.

Due dettagli non ovvi che la demo rende visibili:

- **`get_order_status` normalizza l'identificatore**: `#1042`, `ordine 1042` e `1042 ` sono
  la stessa cosa, e un ordine inesistente restituisce `found: false` con l'invito a
  verificare il numero — **non** un'escalation al primo tentativo (ADR-011).
- **`escalate_to_human` è idempotente per sessione *e* motivo**: un cliente che ripete un
  reclamo non genera un secondo ticket, ma lo stesso cliente che segnala merce danneggiata
  *e* chiede un operatore ne genera legittimamente due (ADR-048). Il `session_id` non è un
  argomento del tool: arriva dal `RunnableConfig`, perché il modello non deve poterlo
  scegliere, inventare od omettere (ADR-047).
"""
)

code(
    """
result = subprocess.run(
    [sys.executable, "scripts/demo_tools.py"], capture_output=True, text=True, check=False
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr[-2000:])
"""
)

# =====================================================================================
# 6. Demo dell'agente
# =====================================================================================

md(
    """
---
## 6. L'agente

`create_agent` di LangChain 1.x con `ChatLiteLLM`, i tre tool, output strutturato nativo e
checkpointer per la memoria di sessione. Temperatura **0.0**, non genericamente «bassa»:
l'evaluation confronta due esecuzioni prima e dopo un intervento, e con temperatura maggiore
di zero il rumore di campionamento comparirebbe come differenza di punteggio che nessuna
modifica ha causato (ADR-050).

Il contratto della risposta è a quattro campi, e **tre su quattro non sono generati
dall'LLM** (ADR-002):

- `sources` = ciò che il modello cita **∩** ciò che il retrieval ha davvero restituito sopra
  soglia. Una fonte inventata non può sopravvivere all'intersezione.
- `needs_human` = vero se e solo se la sessione ha un ticket di escalation aperto, letto dal
  registro su file, non da un giudizio del modello.
- `confidence` = il minimo fra quella proposta dal modello e un **cap deterministico** basato
  sulla qualità del retrieval. Il cap non alza mai la confidence: la limita.
"""
)

code(
    """
import textwrap

from greenthumb.service import build_chat_service, new_session_id


def show(turn, title: str) -> None:
    \"\"\"Print one turn's four-field contract plus how it was produced.

    Args:
        turn: The completed turn returned by ``chat_detailed``.
        title: A heading for the block.
    \"\"\"
    print("=" * 92)
    print(title)
    print("=" * 92)
    print(textwrap.fill(turn.response.answer, 92))
    print()
    print(f"  confidence  : {turn.response.confidence}")
    print(f"  sources     : {turn.response.sources or '— (nessuna)'}")
    print(f"  needs_human : {turn.response.needs_human}")
    print(f"  tool usati  : {turn.tools_invoked or '— (nessuno)'}")
    print()


if HAS_KEY:
    import tempfile

    from greenthumb.escalations_repository import EscalationsRepository

    # Registro dei ticket su file temporaneo, non su quello di esercizio: eseguire il
    # notebook due volte non deve accumulare ticket, altrimenti il numero mostrato negli
    # output cambia a ogni esecuzione e smette di essere riproducibile.
    _registry_dir = tempfile.mkdtemp(prefix="greenthumb-notebook-")
    service = build_chat_service(
        escalations=EscalationsRepository(pathlib.Path(_registry_dir) / "escalations.jsonl")
    )
    print(f"Agente pronto. Registro escalation temporaneo: {_registry_dir}")
else:
    print("Chiave assente: sezione saltata.")
"""
)

md(
    """
### L'esempio della traccia

Una domanda, due strumenti: lo stato dell'ordine **e** la guida di coltivazione. L'agente
deve scomporre la richiesta e rispondere a entrambe le parti in un unico messaggio. Si noti
che i dati dell'ordine **non** compaiono fra le `sources`: una fonte è un documento della
knowledge base, non un record strutturato.
"""
)

code(
    """
if HAS_KEY:
    turn = service.chat_detailed(
        "Quando arriva il mio ordine 1042? Posso piantare adesso i bulbi di tulipano?",
        new_session_id(),
    )
    show(turn, "Esempio della traccia — orchestrazione di due tool")
"""
)

md(
    """
### Escalation, e un rifiuto che non è un'escalation

Due casi che si assomigliano e vanno trattati in modo opposto. Una richiesta esplicita di
parlare con una persona apre un ticket; una domanda fuori ambito — non legata al
giardinaggio o al negozio — riceve un **rifiuto cortese e nessun ticket**, perché generare
una pratica per ogni domanda irrilevante sommergerebbe gli operatori (SPEC §8).

Si osservi la `confidence` del rifiuto: `medium`. Un turno in cui non è stato invocato alcun
tool non può dichiarare confidenza alta, perché un rifiuto legittimo e una risposta non
ancorata alla knowledge base hanno **la stessa impronta osservabile**, e il cap si decide
sul peggiore dei due (ADR-058).
"""
)

code(
    """
if HAS_KEY:
    session = new_session_id()
    show(
        service.chat_detailed("Vorrei parlare con un operatore umano, per favore.", session),
        "Escalation su richiesta esplicita del cliente",
    )
    show(
        service.chat_detailed("Mi consigliate un buon ristorante in centro a Milano?", new_session_id()),
        "Domanda fuori ambito — rifiuto cortese, nessun ticket",
    )
"""
)

md(
    """
### Una fonte inventata non arriva al cliente

Il livello deterministico si può esercitare **senza** modello, costruendo a mano la traccia
di un turno. Qui il modello dichiara di aver usato due documenti, ma il retrieval ne ha
restituito uno solo: l'intersezione scarta l'altro. È il meccanismo che rende impossibile
pubblicare una fonte inesistente (ADR-002).
"""
)

code(
    """
from greenthumb.response import RetrievedChunk, TurnEvidence, build_chat_response
from greenthumb.schemas import AgentOutput

evidence = TurnEvidence(
    retrieved=[
        RetrievedChunk(
            doc_id="guides/bulbi_autunnali.md",
            score=0.88,
            chunk_id="guides/bulbi_autunnali.md#1",
            text="I bulbi si piantano da metà ottobre a fine novembre.",
        )
    ],
    best_similarity=0.88,
    retrieval_ran=True,
)
claimed = AgentOutput(
    answer="I bulbi si piantano da metà ottobre a fine novembre.",
    proposed_confidence="high",
    cited_sources=["guides/bulbi_autunnali.md", "policies/inventata_dal_modello.md"],
)
assembled = build_chat_response(
    output=claimed,
    evidence=evidence,
    needs_human=False,
    score_low=settings.retrieval_score_low,
    score_high=settings.retrieval_score_high,
)
print(f"Il modello dichiara : {claimed.cited_sources}")
print(f"Il retrieval ha dato: {[chunk.doc_id for chunk in evidence.retrieved]}")
print(f"Nella risposta      : {assembled.sources}")
print()
print("Cap sulla confidence, a parità di risposta del modello (proposta: high):")
for label, ev in (
    ("miglior score 0.88 (>= soglia alta)", evidence),
    (
        "miglior score 0.82 (fra le soglie)",
        TurnEvidence(
            retrieved=[RetrievedChunk("guides/bulbi_autunnali.md", 0.82, "c", "...")],
            best_similarity=0.82,
            retrieval_ran=True,
        ),
    ),
    ("retrieval usato, nulla sopra soglia", TurnEvidence(best_similarity=0.74, retrieval_ran=True)),
    ("nessun tool invocato", TurnEvidence()),
):
    out = build_chat_response(
        output=claimed, evidence=ev, needs_human=False,
        score_low=settings.retrieval_score_low, score_high=settings.retrieval_score_high,
    )
    print(f"  {label:38s} -> {out.confidence}")
"""
)

# =====================================================================================
# 7. Memoria
# =====================================================================================

md(
    """
---
## 7. La memoria a breve termine

**Strategia: summarization, non trimming.** Nel customer care le entità citate all'inizio —
un numero d'ordine — vengono riprese molti turni dopo («e quello di prima?»), e il trimming
le perderebbe insieme ai messaggi più vecchi (ADR-004). Il costo è una chiamata al modello in
più quando scatta la soglia.

Il prompt di summarization è **personalizzato, e non per estetica**: quello predefinito del
middleware è scritto per un agente di programmazione, con sezioni `SESSION INTENT` /
`ARTIFACTS` / `NEXT STEPS`, e butterebbe via esattamente ciò che qui deve sopravvivere
(ADR-028). Il nostro impone di conservare numeri d'ordine, SKU, ticket aperti e vincoli
espressi dal cliente.

La demo abbassa il trigger per attraversare la soglia in pochi turni; in produzione vale
6000 token.
"""
)

code(
    """
if HAS_KEY:
    result = subprocess.run(
        [sys.executable, "scripts/demo_memory.py"], capture_output=True, text=True, check=False
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr[-2000:])
else:
    print("Chiave assente: sezione saltata.")
"""
)

md(
    """
**Una lezione che vale più del meccanismo.** Con il trigger corretto, il test di memoria è
diventato rosso su una cosa inattesa: il riassunto *conteneva* «Ordine 1042» ed era in
contesto, eppure alla domanda «mi ricorda il numero del mio ordine?» l'agente rispondeva di
non avere accesso ai dati del cliente. Non era un difetto della memoria, era il system
prompt: la regola «se il cliente parla del suo ordine senza dare il numero, chiediglielo»
veniva applicata all'ultimo messaggio invece che alla conversazione, e la regola di
grounding «non inventare mai numeri d'ordine» faceva il resto.

Un meccanismo di memoria può funzionare perfettamente e **non servire a nulla**, se le
istruzioni dell'agente non gli dicono che quella memoria è conoscenza legittima (ADR-057).
"""
)

# =====================================================================================
# 8. Evaluation
# =====================================================================================

md(
    """
---
## 8. Evaluation

20 conversazioni, 50 turni, 12 multi-turno. Il replay e il calcolo dei punteggi sono
**separati**: `eval/runner.py` salva una traccia per turno e i moduli delle metriche leggono
le tracce, così ricalcolare un punteggio non richiede di rieseguire l'agente. Le tracce sono
versionate nel repository — non sono un artefatto rigenerabile: ricostruirle costa ~300
chiamate e viene diverso, perché OpenRouter smista le richieste fra fornitori a monte
(ADR-073, ADR-030).

Il **modello giudice è configurabile e distinto** da quello dell'agente, per ridurre il bias
di auto-valutazione, ed è validato in modo pigro: il notebook gira con il solo segreto
dell'agente (ADR-010).
"""
)

code(
    """
import json

RESULTS = REPO_DIR / "eval" / "results"

deterministic = json.loads((RESULTS / "deterministic.json").read_text(encoding="utf-8"))
ragas = json.loads((RESULTS / "ragas.json").read_text(encoding="utf-8"))["summary"]
deepeval = json.loads((RESULTS / "deepeval.json").read_text(encoding="utf-8"))["summary"]

print(f"Turni valutati: {deterministic['turns']}\\n")
print("METRICHE DETERMINISTICHE")
for score in deterministic["overall"]:
    value = "n/d" if score["value"] is None else f"{score['value']:7.1%}"
    print(f"  {score['name']:32s} {value}   ({score['passed']}/{score['total']})")

print("\\nRAGAS")
for name, row in ragas.items():
    print(f"  {name:32s} {row['mean']:7.3f}   ({row['turns']} turni, {row['missing']} mancanti)")

print("\\nDEEPEVAL")
for name, row in deepeval.items():
    print(f"  {name:32s} {row['mean']:7.3f}   ({row['items']} item, {row['missing']} mancanti)")
"""
)

md(
    """
### Per categoria

Il valore di una tabella per categoria è mostrare **dove** il sistema cede, non che la media
è buona.
"""
)

code(
    """
INTERESTING = ("needs_human accuracy", "tool selection accuracy", "source recall")


def cell(scores: list[dict], name: str) -> str:
    \"\"\"Format one metric for the per-category table.

    Args:
        scores: Every score of one category.
        name: The metric to format.

    Returns:
        A percentage with the fraction it comes from, or ``n/d`` when it does not apply.
    \"\"\"
    score = next(s for s in scores if s["name"] == name)
    shown = "n/d" if score["value"] is None else f"{score['value']:.0%}"
    return f"{shown} ({score['passed']}/{score['total']})"


header = f"{'categoria':20s}" + "".join(f"{n.split()[0]:>18s}" for n in INTERESTING)
print(header)
print("-" * len(header))
for category, scores in sorted(deterministic["by_category"].items()):
    print(f"{category:20s}" + "".join(f"{cell(scores, n):>18s}" for n in INTERESTING))
"""
)

md(
    """
### L'intervento correttivo, misurato

Le metriche con cui giudicare l'intervento sono state **dichiarate prima di eseguirlo**,
perché scegliere la metrica dopo aver visto i risultati significa scegliere quella che dice
ciò che si sperava (ADR-046).

| Ruolo | Metrica | Prima | Dopo |
|---|---|---|---|
| **Primaria** | `needs_human accuracy` | 86,0% (37/43) | **95,3% (41/43)** |
| **Secondaria** | `escalation_correctness` | 0.692 | **0.725** |
| Guardia | `tool selection accuracy` | 82,5% | 82,5% |
| Guardia | `answer_relevancy` | 0.908 | **0.884** |

**La diagnosi.** I sei errori sul flag `needs_human` andavano in **due direzioni opposte**:
due escalation di troppo su domande di policy a cui la knowledge base risponde — l'agente
apriva un ticket *invece* di rispondere — e quattro mancate dove la specifica le impone, fra
cui un caso di sicurezza (un cane che ingerisce un bulbo) gestito nel merito ma senza
ticket. Una regola applicata al contrario in metà dei casi non è una regola poco seguita: è
una regola letta come **facoltativa**. Nel system prompt i sette criteri erano elencati, non
vincolanti.

**L'intervento**: la sezione sull'escalation diventa due regole esplicite — «se la knowledge
base risponde, rispondi» e «se il caso ricade in uno di questi criteri, apri il ticket,
sempre, anche quando hai già risposto nel merito».

**I due costi, dichiarati.** Una regressione introdotta dall'intervento (il secondo
tentativo su un ordine inesistente confermato non escala più) e un calo di 0.024 su
`answer_relevancy`, perché dove l'agente ora apre un ticket la risposta tende a diventare
*solo* il ticket: la parte informativa sulla tossicità del bulbo, presente nella prima
esecuzione, è sparita. Rendere obbligatorio il ticket ha spostato il peso della risposta dal
contenuto alla procedura, ed è la direzione del prossimo intervento (ADR-071).

### Il reperto più istruttivo

`summarization fired (memory)` valeva **0/2** mentre `knowledge_retention` valeva **1.000**.
Letti insieme, i due numeri dimostrano che il punteggio perfetto di retention **non misurava
nulla**: la soglia non era mai stata superata, quindi il numero d'ordine del primo turno
sopravviveva perché niente era stato riassunto.

Misurando — offline, col contatore di token del middleware — è emerso che le conversazioni
finivano a ~2 900 e ~2 400 token contro una soglia di 8 000: la stima di ~1 000 token per
turno su cui la soglia era stata tarata era sbagliata, la crescita reale è ~600. Soglia
ricalibrata a 6 000 e conversazioni portate a dieci turni: ora la summarization scatta
(2/2) e `knowledge_retention` **scende** a 0.950. Quella discesa è il risultato buono: per
la prima volta il numero misura il meccanismo che dichiara di misurare (ADR-072).

### Due artefatti di metrica, documentati e non corretti

`faithfulness` e `context_precision` valgono 0.000 sulla categoria `edge_cases`, perché un
rifiuto non contiene affermazioni da sostenere e una metrica che misura quante affermazioni
sono supportate dai contesti non può che dare zero. `answer_relevancy` scende a 0.608 sulla
stessa categoria, dove la risposta corretta è *non* rispondere. Escludere i rifiuti dalle
popolazioni sarebbe legittimo — ma deciderlo **dopo** aver visto i numeri è esattamente la
scelta della metrica a posteriori da cui ci si è guardati. Restano nei numeri come limite
dichiarato.

Il report completo, con i tre casi peggiori analizzati, è in
[`eval/results/summary.md`](eval/results/summary.md).
"""
)

code(
    """
# Rieseguire l'evaluation completa costa circa 300 chiamate al modello (agente + tre
# giudici) e richiede GREENTHUMB_EVAL_MODEL. Il notebook carica i risultati salvati; chi
# vuole rieseguire tolga il commento.
#
# subprocess.run([sys.executable, "-m", "eval.runner"], check=True)
# subprocess.run([sys.executable, "-m", "eval.metrics_deterministic"], check=True)
# subprocess.run([sys.executable, "-m", "eval.metrics_ragas"], check=True)
# subprocess.run([sys.executable, "-m", "eval.metrics_deepeval"], check=True)
# subprocess.run([sys.executable, "-m", "eval.report"], check=True)
print("Risultati caricati dal repository. Cella di riesecuzione presente ma commentata.")
"""
)

# =====================================================================================
# 9. API
# =====================================================================================

md(
    """
---
## 9. Deploy locale: l'API FastAPI

Il corpo di `POST /chat` contiene **esattamente** i quattro campi della traccia. Tutto ciò
che il chiamante ha comunque bisogno di sapere viaggia negli header: `X-Session-Id` per
continuare una conversazione e `X-Fallback` perché un guasto del provider resti osservabile
senza alterare il JSON (ADR-009, ADR-074).

Qui uvicorn gira in un thread. In locale:

```bash
make index && make serve
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \\
  -d '{"message": "Quando arriva il mio ordine 1042?"}'
```
"""
)

code(
    """
import threading
import time

if HAS_KEY:
    import uvicorn

    from greenthumb.api import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8111, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(60):
        if server.started:
            break
        time.sleep(1)
    print(f"Server avviato: {server.started}")
else:
    print("Chiave assente: sezione saltata.")
"""
)

code(
    """
if HAS_KEY and server.started:
    import requests

    BASE = "http://127.0.0.1:8111"

    print("GET /health")
    print(json.dumps(requests.get(f"{BASE}/health", timeout=30).json(), indent=2, ensure_ascii=False))

    print("\\nPOST /chat — esempio della traccia")
    reply = requests.post(
        f"{BASE}/chat",
        json={"message": "Quando arriva il mio ordine 1042? Posso piantare adesso i bulbi di tulipano?"},
        timeout=120,
    )
    session = reply.headers["X-Session-Id"]
    print(f"  status           : {reply.status_code}")
    print(f"  X-Session-Id     : {session}")
    print(f"  X-Fallback       : {reply.headers.get('X-Fallback', '(assente)')}")
    print(f"  campi del corpo  : {sorted(reply.json())}")
    print(json.dumps(reply.json(), indent=2, ensure_ascii=False))

    print("\\nPOST /chat — secondo turno nella stessa sessione")
    follow_up = requests.post(
        f"{BASE}/chat",
        json={"message": "E a che profondità vanno piantati?", "session_id": session},
        timeout=120,
    )
    print(json.dumps(follow_up.json(), indent=2, ensure_ascii=False))

    print("\\nInput non valido e reset della sessione")
    print(f"  messaggio vuoto -> {requests.post(f'{BASE}/chat', json={'message': ''}, timeout=30).status_code}")
    print(f"  DELETE sessione -> {requests.delete(f'{BASE}/sessions/{session}', timeout=30).status_code}")
"""
)

# =====================================================================================
# 10. Relazione
# =====================================================================================

md(
    """
---
# 10. Relazione tecnica

## 10.1 Il principio che governa l'architettura

**Deterministico prima del probabilistico.** L'LLM decide *cosa dire* e *quale strumento
usare*; tutto ciò che può essere calcolato dal codice viene calcolato dal codice.

Concretamente, dei quattro campi della risposta **uno solo** è generato dal modello:

| Campo | Origine | Perché |
|---|---|---|
| `answer` | LLM | è il testo per il cliente |
| `sources` | codice | intersezione fra ciò che il modello cita e ciò che il retrieval ha davvero restituito sopra soglia |
| `needs_human` | codice | derivato dal registro delle escalation della sessione, un file |
| `confidence` | entrambi | minimo fra la proposta del modello e un cap basato sugli score del retrieval |

Il guadagno non è teorico: una fonte inventata **non può** raggiungere il cliente, e un
flag incoerente con le azioni svolte non è rappresentabile. In più, tre metriche
dell'evaluation diventano calcolabili senza giudice, e quindi gratuite e ripetibili.

Il prezzo è un livello di assemblaggio in più (`response.py`) e la necessità che i tool
restituiscano i propri metadati come *artifact* leggibile. Era il rischio architetturale più
grave del progetto — se il passo di output strutturato avesse nascosto i `ToolMessage`,
l'intero disegno sarebbe stato irrealizzabile — ed è stato verificato con uno spike **prima**
di scrivere una riga di codice di produzione (ADR-027).

## 10.2 La memoria, nelle sue due forme

**Lungo termine, semantica**: knowledge base di 37 documenti, chunking guidato dagli
heading, embedding locali `multilingual-e5-base`, Chroma persistente, top-k 4 con soglia
calibrata. Locale e non via API: nessun costo di indicizzazione e nessun secondo provider da
configurare su Colab (ADR-005).

**Breve termine, esplicita**: summarization con trigger a 6000 token e ultimi 6 messaggi
mantenuti integri, checkpointer in memoria con `thread_id = session_id`.

La scelta di summarization invece di trimming è il punto da argomentare. Nel customer care
la conversazione tipica cita un numero d'ordine al primo turno e lo riprende molti turni
dopo in forma pronominale. Il trimming, che scarta i messaggi più vecchi, perderebbe
proprio l'entità più utile. L'alternativa più robusta — trimming più estrazione delle entità
in uno stato strutturato — sarebbe più deterministica e va citata come evoluzione naturale:
costa più codice, e il riassunto ha il vantaggio di conservare anche i vincoli sfumati
(«coltivo sul balcone, poco sole») che nessuno schema di entità avrebbe previsto.

Tre cose, su questo meccanismo, le ha insegnate solo la misura:

1. **La soglia non si confronta con i token della conversazione**, ma con il totale che il
   provider riporta per l'intera richiesta, schemi dei tool e system prompt inclusi. Il
   valore inizialmente previsto, 2500, era *sotto il pavimento* di 2583 della prima
   chiamata: la summarization sarebbe scattata prima di ogni singola chiamata, e nessun test
   lo avrebbe rilevato — i test di memoria sarebbero stati *più* verdi, non meno. Il sintomo
   sarebbe arrivato dalla bolletta (ADR-056).
2. **Una memoria che funziona può non servire a nulla** se il prompt non la considera
   conoscenza legittima (ADR-057, sezione 7).
3. **Una retention perfetta può misurare il nulla.** Finché la soglia non viene superata, il
   dato del primo turno sopravvive banalmente. La metrica che lo ha smascherato esisteva
   proprio per questo (ADR-072).

## 10.3 Cosa dice l'evaluation, e cosa non può dire

I numeri sono nella sezione 8. Qui conta il metodo.

**Tre livelli di misura, con fiducia decrescente.** Le metriche deterministiche confrontano
fatti con fatti e non hanno margine d'errore. Le metriche RAGAS misurano la risposta contro
i contesti recuperati, che sono dati reali, ma col giudizio di un modello. Le metriche
DeepEval giudicano qualità e pertinenza, e sono le più esposte alla calibrazione del
giudice — due di esse danno punteggi bassi su comportamenti **corretti**, come documentato.

**Il dataset è ground truth, quindi va verificato come tale.** Diciassette test lo
confrontano con la knowledge base e gli ordini reali, caricati dagli stessi moduli che usa
l'agente: un `doc_id` sbagliato non solleverebbe nulla, abbasserebbe `source_recall` in
silenzio, e il report attribuirebbe all'agente un difetto del dataset. Alla prima esecuzione
quei test hanno trovato tre difetti reali (ADR-063).

**Ciò che l'evaluation non può dire.** Venti conversazioni misurano venti conversazioni. Un
terzo dei fallimenti di `source recall` dipende da aspettative troppo strette del dataset —
l'agente cita una guida diversa che contiene lo stesso dato e risponde correttamente — e
quelle aspettative **non** sono state allargate a posteriori, perché ritoccare il ground
truth dopo aver visto la metrica è il modo più rapido di rendere inutile un benchmark
(ADR-045). Resta inoltre la variabilità del fornitore: OpenRouter smista fra infrastrutture
a monte e il pinning non è implementabile attraverso LiteLLM, quindi due esecuzioni
identiche possono divergere — se n'è visto un caso pulito, lo stesso turno che cerca nella
knowledge base in un'esecuzione e non cerca in un'altra, a prompt identico (ADR-030).

## 10.4 Il costo di un ecosistema in movimento

Vale la pena registrarlo, perché è la parte del lavoro che nessuna specifica prevede.

- `import ragas` falliva all'installazione pulita: RAGAS importa `ChatVertexAI` da
  `langchain_community` in modo incondizionato, e la 0.4.x di quel pacchetto ha svuotato
  `chat_models/`. Serve un pin esplicito a `0.3.31`, l'unica versione che contiene ancora
  quel modulo *ed* è compatibile con il core richiesto da langchain 1.4.2. Il pin è fragile
  per costruzione e va rivisitato a ogni aggiornamento (ADR-019).
- `import deepeval` chiama `load_dotenv()` come effetto collaterale e installa un plugin
  pytest: i test unitari sono diventati rossi **nel momento in cui è comparso un `.env`**,
  senza che una riga di codice cambiasse. L'isolamento dei test dalla configurazione locale
  va imposto attivamente, e si è ripresentato da tre direzioni diverse prima di essere
  chiuso (ADR-025, ADR-044).
- Un parametro annotato `RunnableConfig | None = None` — la scrittura apparentemente
  prudente — **disattiva l'iniezione** del contesto e, con schema inferito, espone il
  parametro fra quelli che il modello può riempire. Tutte le conversazioni finivano in
  un'unica sessione condivisa, senza alcun errore (ADR-047).
- Gli avvertimenti ereditati vanno misurati sul proprio corpus: «senza i prefissi e5 la
  qualità del retrieval crolla in modo silenzioso» **non è confermato** da nessuna delle
  quattro misure fatte. I prefissi si mantengono perché sono l'uso documentato del modello e
  non costano nulla, non perché siano critici (ADR-046).

Il filo comune è il **fallimento silenzioso**: nessuno di questi problemi produce un errore.
Producono numeri sbagliati, sessioni condivise, filtri disattivati. È la ragione per cui in
questo progetto i valori di configurazione che disattivano un presidio non sono valori
ammissibili: un validatore rifiuta una soglia di rilevanza a zero e un trigger di
summarization sotto il pavimento misurato, citando il valore corretto e il documento che lo
giustifica (ADR-043, ADR-056).

## 10.5 Limiti noti

Dichiarati, non nascosti:

- **Nessuna autenticazione del cliente.** `get_order_status` rivela i dettagli di un ordine
  a chiunque ne conosca il numero. In produzione servirebbe verificare l'identità
  confrontando l'email dell'ordine. È il limite più serio del sistema.
- **Sessioni volatili.** Il checkpointer è in memoria: un riavvio del processo perde tutte
  le conversazioni. Lo scambio con un checkpointer persistente è un argomento.
- **Venti conversazioni di evaluation** sono un campione piccolo, e due metriche giudicate
  penalizzano comportamenti corretti (i rifiuti).
- **Un difetto residuo misurato e non corretto**: su una domanda di policy a cui la
  knowledge base risponde, l'agente apre ancora un ticket invece di rispondere. Una seconda
  iterazione sul prompt è l'ipotesi naturale, ma accumulare modifiche eseguendo l'evaluation
  dopo ognuna porta al sovradattamento su venti conversazioni.
- **Riproducibilità imperfetta** per il routing di OpenRouter fra fornitori a monte.
- **Un dettaglio estetico**: il middleware di summarization premette al riassunto una frase
  **in inglese** non configurabile, dentro una conversazione interamente italiana.

## 10.6 Sviluppi futuri

- Autenticazione del cliente e checkpointer persistente: i due limiti di cui sopra.
- **Ricerca con diversificazione (MMR).** Sulla domanda sulle forbici i quattro risultati di
  top-k sono tutti sezioni dello stesso documento: su una domanda a due facce — un prodotto
  *e* una policy — il top-k può esaurirsi su un solo documento e lasciare metà domanda senza
  fonte. È un'ipotesi già formulata e misurabile (ADR-068).
- **Re-ranking** come esperimento misurato, con e senza.
- **Trimming più stato strutturato delle entità** come alternativa più deterministica alla
  summarization.
- **Il ticket in aggiunta alla risposta, non al posto suo**: la direzione indicata dal costo
  misurato dell'intervento correttivo.

---

## Documenti del repository

| Documento | Contenuto |
|---|---|
| `docs/DECISIONS.md` | 75 decisioni architetturali con contesto, alternative scartate e conseguenze |
| `docs/CONVENTIONS.md` | convenzioni di codice e insidie delle librerie, con i numeri che le smentiscono |
| `docs/SPEC.md` | specifica tecnica e tracciabilità dei requisiti |
| `docs/PLAN.md` | piano di lavoro con Definition of Done per fase |
| `eval/results/summary.md` | report dell'evaluation, generato, con l'analisi dei casi peggiori |
| `docs/RETRIEVAL_CALIBRATION.md` | tabelle complete della calibrazione delle soglie |
"""
)


def main() -> None:
    """Write the notebook to disk."""
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata.update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
            "colab": {"provenance": [], "toc_visible": True},
        }
    )
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, NOTEBOOK_PATH)
    markdown = sum(1 for cell in cells if cell.cell_type == "markdown")
    print(
        f"Scritto {NOTEBOOK_PATH}: {len(cells)} celle ({markdown} markdown, {len(cells) - markdown} codice)"
    )


if __name__ == "__main__":
    main()
