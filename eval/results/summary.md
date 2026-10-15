# Risultati dell'evaluation

Generato da `eval/report.py` il 2026-10-15. 20 conversazioni, 43 turni.

Tutto cio' che precede la sezione *Analisi* e' generato: i numeri vengono da `traces.jsonl`, `deterministic.json`, `ragas.json` e `deepeval.json`, in questa stessa cartella, e nessuna cifra e' stata trascritta a mano. L'analisi, che non si puo' calcolare, e' scritta in `analysis.md` e inclusa qui alla fine.

## Metriche deterministiche

| Metrica | Valore | Turni |
|---|---|---|
| needs_human accuracy | 86.0% | 37/43 |
| tool selection accuracy | 82.5% | 33/40 |
| source recall | 50.0% | 14/28 |
| schema validity | 100.0% | 43/43 |
| answered without fallback | 100.0% | 43/43 |
| summarization fired (memory) | 0.0% | 0/2 |

### Per categoria

| Categoria | needs_human accuracy | tool selection accuracy | source recall | schema validity | answered without fallback | summarization fired (memory) |
|---|---|---|---|---|---|---|
| `agronomic_advice` | 100.0% (4/4) | 100.0% (4/4) | 75.0% (3/4) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `edge_cases` | 75.0% (3/4) | 66.7% (2/3) | n/d (0/0) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `escalation` | 62.5% (5/8) | 50.0% (4/8) | 20.0% (1/5) | 100.0% (8/8) | 100.0% (8/8) | n/d (0/0) |
| `memory` | 100.0% (13/13) | 90.9% (10/11) | 37.5% (3/8) | 100.0% (13/13) | 100.0% (13/13) | 0.0% (0/2) |
| `multi_tool` | 75.0% (3/4) | 100.0% (4/4) | 75.0% (3/4) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `order_status` | 100.0% (3/3) | 100.0% (3/3) | n/d (0/0) | 100.0% (3/3) | 100.0% (3/3) | n/d (0/0) |
| `product_info` | 100.0% (4/4) | 75.0% (3/4) | 50.0% (2/4) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `returns_policy` | 66.7% (2/3) | 100.0% (3/3) | 66.7% (2/3) | 100.0% (3/3) | 100.0% (3/3) | n/d (0/0) |

### Turni che non rispettano l'attesa

- **needs_human accuracy**: conv_09#1, conv_13#2, conv_16#1, conv_16#2, conv_16#3, conv_20#2
- **tool selection accuracy**: conv_01#1, conv_15#2, conv_16#1, conv_16#2, conv_16#3, conv_17#4, conv_20#2
- **source recall**: conv_01#1, conv_02#2, conv_06#1, conv_09#1, conv_13#2, conv_15#2, conv_16#1, conv_16#2, conv_16#3, conv_17#2, conv_17#3, conv_17#4, conv_18#2, conv_18#3
- **summarization fired (memory)**: conv_17#7, conv_18#6

## Metriche RAGAS

| Metrica | Media | Valutati | Mancanti |
|---|---|---|---|
| context_precision_with_reference | 0.798 | 23 | 0 |
| faithfulness | 0.754 | 23 | 0 |

### Per categoria

| Metrica | Categoria | Media |
|---|---|---|
| context_precision_with_reference | `agronomic_advice` | 0.958 |
| context_precision_with_reference | `edge_cases` | 0.000 |
| context_precision_with_reference | `escalation` | 0.778 |
| context_precision_with_reference | `memory` | 0.813 |
| context_precision_with_reference | `multi_tool` | 0.778 |
| context_precision_with_reference | `product_info` | 0.778 |
| context_precision_with_reference | `returns_policy` | 0.917 |
| faithfulness | `agronomic_advice` | 0.964 |
| faithfulness | `edge_cases` | 0.000 |
| faithfulness | `escalation` | 0.532 |
| faithfulness | `memory` | 0.824 |
| faithfulness | `multi_tool` | 0.610 |
| faithfulness | `product_info` | 0.767 |
| faithfulness | `returns_policy` | 1.000 |

## Metriche DeepEval

| Metrica | Media | Valutati | Mancanti |
|---|---|---|---|
| answer_relevancy | 0.908 | 43 | 0 |
| escalation_correctness | 0.692 | 12 | 0 |
| knowledge_retention | 1.000 | 2 | 0 |

### Per categoria

| Metrica | Categoria | Media |
|---|---|---|
| answer_relevancy | `agronomic_advice` | 0.900 |
| answer_relevancy | `edge_cases` | 0.608 |
| answer_relevancy | `escalation` | 0.938 |
| answer_relevancy | `memory` | 0.925 |
| answer_relevancy | `multi_tool` | 1.000 |
| answer_relevancy | `order_status` | 1.000 |
| answer_relevancy | `product_info` | 1.000 |
| answer_relevancy | `returns_policy` | 0.833 |
| escalation_correctness | `edge_cases` | 0.650 |
| escalation_correctness | `escalation` | 0.713 |
| knowledge_retention | `memory` | 1.000 |

## I 3 casi peggiori

### conv_16#2 — `escalation`

- **Domanda**: Un'altra cosa: nell'ordine 1053 i bulbi sono arrivati ammuffiti.
- **Risposta**: Per i bulbi ammuffiti all'apertura della confezione, come nel suo caso, GreenThumb copre il difetto senza limiti di tempo entro i 24 mesi dalla consegna. Visto che ha già richiesto il reso entro 8 giorni dalla consegna, la sua richiesta è valida e sarà gestita dal nostro servizio clienti. Se ha bisogno di ulteriore assistenza, sono a disposizione.
- **Attese non rispettate**: 3
- **Media dei punteggi giudicati**: 0.650
- `needs_human`: False (atteso True)
- tool: ['get_order_status', 'search_knowledge_base'] (attesi ['search_knowledge_base', 'get_order_status', 'escalate_to_human'])
- fonti: ['policies/resi_rimborsi.md', 'policies/prodotti_deperibili.md'] (attese ['policies/danni_trasporto.md'])

### conv_16#1 — `escalation`

- **Domanda**: Aiuto, il mio cane ha mangiato un bulbo di tulipano. Cosa devo fare?
- **Risposta**: I bulbi di tulipano sono tossici per i cani e possono causare sintomi come vomito, diarrea e irritazione orale. Le consiglio di contattare immediatamente un veterinario per una valutazione e un trattamento adeguato. Nel frattempo, eviti che il cane ingerisca altri bulbi o piante potenzialmente pericolose.
- **Attese non rispettate**: 3
- **Media dei punteggi giudicati**: 0.800
- `needs_human`: False (atteso True)
- tool: — (attesi ['search_knowledge_base', 'escalate_to_human'])
- fonti: — (attese ['products/bulbi_tulipano_triumph.md'])

### conv_16#3 — `escalation`

- **Domanda**: Quanto tempo ci vuole perché qualcuno mi risponda?
- **Risposta**: Generalmente, il nostro servizio clienti risponde alle richieste di reso entro pochi giorni lavorativi. Se la sua pratica è già stata aperta, dovrebbe ricevere un riscontro a breve. Se desidera, posso verificare lo stato attuale della sua richiesta.
- **Attese non rispettate**: 3
- **Media dei punteggi giudicati**: 0.800
- `needs_human`: False (atteso True)
- tool: — (attesi ['search_knowledge_base'])
- fonti: — (attese ['policies/contatti_orari.md'])

## Analisi

### Il quadro in una frase

Il sistema regge dove la domanda è una sola e la risposta sta in un documento
(`product_info`, `order_status`, `multi_tool` e `agronomic_advice` hanno answer relevancy
fra 0.90 e 1.00, context precision 0.958 e faithfulness 0.964 sui consigli agronomici), e
cede su **quando passare la conversazione a una persona**: `needs_human accuracy` all'86,0%
e `escalation_correctness` a 0.692 sono i due numeri peggiori del lotto, e i sei turni che
sbagliano il flag sono anche quelli che trascinano giù tutto il resto.

### Una causa, due sintomi opposti

I sei errori su `needs_human` non sono rumore distribuito: vanno in **due direzioni
contrarie**, e questo dice qual è la causa.

**Escalation di troppo (2 turni).** A «ho ricevuto una bustina di semi dieci giorni fa,
posso ancora restituirla?» (conv_09#1) l'agente ha aperto il ticket ESC-0001 e ha risposto
*soltanto* questo: «la sua richiesta di informazioni sul reso è stata presa in carico». La
domanda aveva una risposta precisa nella KB — sì, dieci giorni rientrano nei quattordici
dei deperibili — e il cliente ha ricevuto un numero di pratica al posto della risposta.
Identico su conv_13#2 con il sacco di terriccio (ESC-0002). È il peggior modo di sbagliare
in un customer care di primo livello: il ticket aperto senza bisogno costa lavoro a un
operatore e lascia il cliente senza ciò che aveva chiesto.

**Escalation mancata (4 turni).** conv_16#1 è il caso serio: «il mio cane ha mangiato un
bulbo di tulipano». L'agente ha risposto correttamente nel merito — tossicità, consiglio di
contattare un veterinario — ma **senza invocare alcun tool** e **senza aprire un ticket**,
quando `safety` è uno dei sette criteri espliciti di SPEC §8. Lo stesso su conv_16#2 (bulbi
ammuffiti, cioè `damaged_or_wrong_item`), conv_16#3 e conv_20#2, dove l'agente ha dichiarato
con onestà di non avere documentazione sull'innesto del melo — il comportamento giusto — ma
non ha trasformato quell'ammissione nel ticket `no_knowledge` che la specifica prevede.

**La causa è una sola**: nel system prompt i sette criteri di escalation sono *elencati* ma
non *vincolanti*. Il modello li legge come una facoltà, e allora li usa dove la domanda gli
sembra impegnativa (una policy sui resi) e li salta dove il merito gli sembra già risolto
(ha già detto al cliente di andare dal veterinario, quindi perché aprire un ticket?). Non è
un difetto di retrieval né di tool: entrambi funzionano quando vengono chiamati.

### Perché `source recall` è al 50%, e quanto di ciò è un difetto

Quattordici turni su ventotto non contengono la fonte attesa. Scomposti per causa, sono tre
gruppi diversi, e solo il primo è un difetto del sistema:

| Causa | Turni | È un difetto? |
|---|---|---|
| Non ha cercato affatto | conv_01#1, conv_15#2, conv_16#1, conv_16#3, conv_17#4 | **Sì** |
| Ha cercato, nulla sopra soglia | conv_09#1, conv_13#2 | Sì, ma di soglia |
| Ha cercato e ha trovato un documento *diverso* che risponde | conv_02#2, conv_06#1, conv_16#2, conv_17#2, conv_17#3, conv_18#2, conv_18#3 | Discutibile |

Il primo gruppo è grave e ha la stessa radice dell'escalation: **conv_01#1 è una domanda
pura di prodotto — il diametro di taglio delle forbici — a cui l'agente ha risposto senza
cercare**, cioè attingendo alla propria conoscenza, che la regola di grounding vieta. Il
dato è corretto (20 mm), il che rende il problema invisibile a chi legge la risposta: è
giusto per caso.

Il terzo gruppo merita onestà. A conv_06#1 («il mio balcone riceve due ore di sole diretto»)
l'agente ha citato `guides/coltivare_in_balcone.md` invece di
`guides/giardinaggio_poca_luce.md`: entrambe le guide contengono la stessa scala di ore di
sole, e la risposta è corretta. A conv_17#2 ha citato tre guide su balcone e luce invece
della scheda del giacinto, e ha risposto bene. **Qui l'aspettativa del dataset è troppo
stretta, non il sistema sbagliato.** Non ho allargato `expected_sources` a posteriori: con
la metrica già vista, ritoccare il ground truth per farla salire è il modo più rapido di
rendere inutile un benchmark (ADR-045). Il limite va dichiarato e lasciato nei numeri.

### Il reperto più importante: la summarization non è mai scattata

`summarization fired (memory)` è **0 su 2**. Le due conversazioni `memory`, da sette e sei
turni, non hanno superato gli 8000 token di soglia. E `knowledge_retention` vale **1.000**.

Letti insieme, i due numeri sono la trappola di ADR-028 nella sua forma più pura: il
punteggio perfetto di retention non dimostra che la memoria regge, dimostra che **non è
stata messa alla prova**. Il numero d'ordine del primo turno è sopravvissuto perché nessun
turno è stato riassunto. ADR-056 aveva previsto «almeno sei turni» stimando ~1000 token per
turno sopra un pavimento di ~2583: la stima era ottimistica, perché i turni di queste due
conversazioni sono brevi. È l'unica metrica del lotto che esiste per smascherare un falso
positivo, e lo ha fatto al primo colpo.

### Due artefatti di metrica, non del sistema

**`faithfulness` 0.000 su conv_20#2** (`edge_cases`). La risposta è «non ho trovato
informazioni nella nostra documentazione sull'innesto a corona»: un rifiuto non contiene
affermazioni, e una metrica che misura quante affermazioni sono sostenute dai contesti non
può che dare zero. Lo stesso vale per `context_precision` a 0.000 sulla categoria. **Non
cambio la popolazione della metrica adesso**: escludere i rifiuti è una raffinatezza
legittima, ma deciderla dopo aver visto il numero è precisamente la scelta della metrica
*a posteriori* contro cui ADR-046 mette in guardia. Resta come limite dichiarato.

**`answer_relevancy` 0.608 su `edge_cases`.** La categoria contiene un rifiuto fuori ambito
(il ristorante a Milano) che *deve* non rispondere alla domanda. La metrica penalizza
esattamente il comportamento corretto. È la stessa calibrazione segnalata in ADR-033, dove
la metrica dava 0.5 a una risposta giusta.

### L'intervento correttivo, e la metrica scelta prima di eseguirlo

Un solo intervento, sul **system prompt**, sulla causa comune: rendere i criteri di
escalation vincolanti in entrambe le direzioni — una domanda a cui la KB risponde va
**risposta** e non trasformata in ticket; un caso che ricade in uno dei sette criteri apre
un ticket **anche quando** l'agente ha già risposto nel merito — e rafforzare l'obbligo di
cercare prima di affermare qualcosa su prodotti, policy o tempi.

**Metriche di giudizio, dichiarate prima della seconda esecuzione** (ADR-046):

| Ruolo | Metrica | Valore di partenza | Atteso |
|---|---|---|---|
| Primaria | `needs_human accuracy` | 86,0% (37/43) | in aumento |
| Secondaria | `escalation_correctness` (GEval) | 0.692 | in aumento |
| Guardia di regressione | `tool selection accuracy` | 82,5% (33/40) | non in calo |
| Guardia di regressione | `answer_relevancy` | 0.908 | non in calo |

`source recall` **non** è fra le metriche di giudizio, perché un terzo dei suoi fallimenti
dipende da aspettative troppo strette del dataset e non dal comportamento dell'agente:
usarla per giudicare l'intervento misurerebbe in parte il dataset.

## Confronto prima/dopo

_Da compilare dopo la seconda esecuzione._
