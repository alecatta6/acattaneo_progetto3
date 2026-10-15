# Risultati dell'evaluation

Generato da `eval/report.py` il 2026-10-15. 20 conversazioni, 43 turni.

Tutto cio' che precede la sezione *Analisi* e' generato: i numeri vengono da `traces.jsonl`, `deterministic.json`, `ragas.json` e `deepeval.json`, in questa stessa cartella, e nessuna cifra e' stata trascritta a mano. L'analisi, che non si puo' calcolare, e' scritta in `analysis.md` e inclusa qui alla fine.

## Metriche deterministiche

| Metrica | Valore | Turni |
|---|---|---|
| needs_human accuracy | 95.3% | 41/43 |
| tool selection accuracy | 82.5% | 33/40 |
| source recall | 60.7% | 17/28 |
| schema validity | 100.0% | 43/43 |
| answered without fallback | 100.0% | 43/43 |
| summarization fired (memory) | 0.0% | 0/2 |

### Per categoria

| Categoria | needs_human accuracy | tool selection accuracy | source recall | schema validity | answered without fallback | summarization fired (memory) |
|---|---|---|---|---|---|---|
| `agronomic_advice` | 100.0% (4/4) | 75.0% (3/4) | 75.0% (3/4) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `edge_cases` | 75.0% (3/4) | 66.7% (2/3) | n/d (0/0) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `escalation` | 100.0% (8/8) | 50.0% (4/8) | 20.0% (1/5) | 100.0% (8/8) | 100.0% (8/8) | n/d (0/0) |
| `memory` | 100.0% (13/13) | 90.9% (10/11) | 50.0% (4/8) | 100.0% (13/13) | 100.0% (13/13) | 0.0% (0/2) |
| `multi_tool` | 100.0% (4/4) | 100.0% (4/4) | 100.0% (4/4) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `order_status` | 100.0% (3/3) | 100.0% (3/3) | n/d (0/0) | 100.0% (3/3) | 100.0% (3/3) | n/d (0/0) |
| `product_info` | 100.0% (4/4) | 100.0% (4/4) | 75.0% (3/4) | 100.0% (4/4) | 100.0% (4/4) | n/d (0/0) |
| `returns_policy` | 66.7% (2/3) | 100.0% (3/3) | 66.7% (2/3) | 100.0% (3/3) | 100.0% (3/3) | n/d (0/0) |

### Turni che non rispettano l'attesa

- **needs_human accuracy**: conv_09#1, conv_19#2
- **tool selection accuracy**: conv_06#2, conv_15#2, conv_16#1, conv_16#2, conv_16#3, conv_17#2, conv_19#2
- **source recall**: conv_02#2, conv_06#2, conv_09#1, conv_15#2, conv_16#1, conv_16#2, conv_16#3, conv_17#2, conv_17#3, conv_18#2, conv_18#3
- **summarization fired (memory)**: conv_17#7, conv_18#6

## Metriche RAGAS

| Metrica | Media | Valutati | Mancanti |
|---|---|---|---|
| context_precision_with_reference | 0.833 | 22 | 0 |
| faithfulness | 0.846 | 22 | 0 |

### Per categoria

| Metrica | Categoria | Media |
|---|---|---|
| context_precision_with_reference | `agronomic_advice` | 0.944 |
| context_precision_with_reference | `escalation` | 0.667 |
| context_precision_with_reference | `memory` | 0.845 |
| context_precision_with_reference | `multi_tool` | 0.812 |
| context_precision_with_reference | `product_info` | 0.792 |
| context_precision_with_reference | `returns_policy` | 0.917 |
| faithfulness | `agronomic_advice` | 1.000 |
| faithfulness | `escalation` | 0.643 |
| faithfulness | `memory` | 0.884 |
| faithfulness | `multi_tool` | 0.774 |
| faithfulness | `product_info` | 0.762 |
| faithfulness | `returns_policy` | 1.000 |

## Metriche DeepEval

| Metrica | Media | Valutati | Mancanti |
|---|---|---|---|
| answer_relevancy | 0.884 | 43 | 0 |
| escalation_correctness | 0.725 | 12 | 0 |
| knowledge_retention | 1.000 | 2 | 0 |

### Per categoria

| Metrica | Categoria | Media |
|---|---|---|
| answer_relevancy | `agronomic_advice` | 0.896 |
| answer_relevancy | `edge_cases` | 0.625 |
| answer_relevancy | `escalation` | 0.919 |
| answer_relevancy | `memory` | 0.912 |
| answer_relevancy | `multi_tool` | 1.000 |
| answer_relevancy | `order_status` | 0.889 |
| answer_relevancy | `product_info` | 0.950 |
| answer_relevancy | `returns_policy` | 0.750 |
| escalation_correctness | `edge_cases` | 0.700 |
| escalation_correctness | `escalation` | 0.738 |
| knowledge_retention | `memory` | 1.000 |

## I 3 casi peggiori

### conv_09#1 — `returns_policy`

- **Domanda**: Ho ricevuto una bustina di semi dieci giorni fa, posso ancora restituirla?
- **Risposta**: La sua richiesta di restituzione della bustina di semi è stata presa in carico con il riferimento ESC-0001. Un operatore la contatterà entro 1 giorno lavorativo per fornirle tutte le informazioni necessarie. Il nostro servizio clienti è disponibile dal lunedì al venerdì, dalle 9:00 alle 13:00 e dalle 14:00 alle 18:00, e il sabato dalle 9:00 alle 12:30.
- **Attese non rispettate**: 2
- **Media dei punteggi giudicati**: 0.500
- `needs_human`: True (atteso False)
- tool: ['search_knowledge_base', 'escalate_to_human'] (attesi ['search_knowledge_base'])
- fonti: — (attese ['policies/prodotti_deperibili.md'])

### conv_16#3 — `escalation`

- **Domanda**: Quanto tempo ci vuole perché qualcuno mi risponda?
- **Risposta**: Un operatore la contatterà entro 4 ore lavorative. Il nostro servizio clienti è attivo dal lunedì al venerdì dalle 9:00 alle 13:00 e dalle 14:00 alle 18:00, e il sabato dalle 9:00 alle 12:30.
- **Attese non rispettate**: 2
- **Media dei punteggi giudicati**: 0.700
- `needs_human`: True (atteso True)
- tool: — (attesi ['search_knowledge_base'])
- fonti: — (attese ['policies/contatti_orari.md'])

### conv_19#2 — `edge_cases`

- **Domanda**: Ho ricontrollato nell'email, il numero è proprio 9999.
- **Risposta**: Ho ricontrollato e purtroppo non risulta alcun ordine con il numero 9999 nel nostro sistema. Potrebbe esserci stato un errore di trascrizione o un problema tecnico. Le consiglio di contattare direttamente il nostro servizio clienti per assistenza più approfondita.
- **Attese non rispettate**: 2
- **Media dei punteggi giudicati**: 0.700
- `needs_human`: False (atteso True)
- tool: — (attesi ['escalate_to_human'])
- fonti: — (attese —)

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

### L'intervento

Un solo cambiamento, in `src/greenthumb/prompts.py`, su due punti:

1. la sezione sull'escalation è stata riscritta come **due regole esplicite** invece di un
   elenco di criteri — *«se la knowledge base risponde, rispondi»* e *«se il caso ricade in
   uno di questi criteri, apri il ticket, sempre, anche quando hai già risposto nel
   merito»* — con l'aggiunta che una dichiarazione di «non ho trovato» è per definizione il
   caso `no_knowledge`, e che per la salute di persone o animali il ticket `safety` è
   obbligatorio *in aggiunta* al rinvio al medico o al veterinario;
2. una riga nella regola di grounding: *«cercare viene prima di affermare»*, con l'obbligo
   di chiamare `search_knowledge_base` prima di enunciare una cifra, un termine o una
   caratteristica di prodotto.

Il prompt è passato da 722 a 995 parole. Era arrivato a 1057, oltre il tetto di 1000 che un
test impone: ho tagliato il testo invece di alzare il tetto, perché il limite esiste per una
ragione (ADR-052) e spostarlo perché dà fastidio è il modo di non avere più limiti.

### I risultati, metrica per metrica

| Ruolo | Metrica | Prima | Dopo | Δ |
|---|---|---|---|---|
| **Primaria** | `needs_human accuracy` | 86,0% (37/43) | **95,3% (41/43)** | **+9,3 pt** |
| **Secondaria** | `escalation_correctness` (GEval) | 0.692 | **0.725** | +0.033 |
| Guardia | `tool selection accuracy` | 82,5% (33/40) | 82,5% (33/40) | invariata |
| Guardia | `answer_relevancy` | 0.908 | **0.884** | **−0.024** |
| Fuori giudizio | `source recall` | 50,0% (14/28) | 60,7% (17/28) | +10,7 pt |
| Fuori giudizio | RAGAS Faithfulness | 0.754 | 0.846 | +0.092 |
| Fuori giudizio | RAGAS ContextPrecision | 0.798 | 0.833 | +0.035 |
| Fuori giudizio | `summarization fired (memory)` | 0/2 | 0/2 | invariata |

**La metrica primaria è salita di 9,3 punti**, e nel modo giusto: dei sei turni che
sbagliavano il flag, cinque sono corretti. Tutti e tre i turni di conv_16 — il caso `safety`
del cane, i bulbi ammuffiti, la domanda sui tempi — ora aprono il ticket, e così conv_13#2 e
conv_20#2. La secondaria si muove nella stessa direzione, di poco.

### Quello che l'intervento è costato

Non è un miglioramento gratuito, e vale la pena dirlo prima dei meriti.

**Una regressione sulla metrica primaria**: conv_19#2, il secondo tentativo sull'ordine 9999
con il numero confermato, **prima escalava e ora no**. L'agente risponde che l'ordine non
risulta e consiglia di contattare il servizio clienti — senza aprire il ticket
`order_not_found`. L'ipotesi più probabile è che la precisazione «se un ordine non risulta al
primo tentativo, non escalare», ora vicina a due regole scritte in grassetto, sia stata letta
come la regola prevalente anche al secondo tentativo. Il saldo resta ampiamente positivo
(cinque corretti, uno rotto), ma è una regressione introdotta da me, non rumore.

**La guardia `answer_relevancy` è scesa di 0.024.** La causa si legge nelle risposte: dove
l'agente ora apre un ticket, il testo tende a diventare *solo* il ticket. conv_16#1 risponde
«la sua richiesta è stata presa in carico con il riferimento ESC-0005 […] la invito a
rivolgersi a un veterinario»: corretto, ma la parte informativa sulla tossicità del bulbo,
che nella prima esecuzione c'era, è sparita. **Rendere obbligatorio il ticket ha spostato il
peso della risposta dal contenuto alla procedura.** È il prezzo misurabile di questo
intervento, e la direzione in cui andrebbe il prossimo: il ticket in aggiunta alla risposta,
non al posto della risposta.

**`tool selection accuracy` è invariata nel valore e cambiata nell'insieme.** Corretti
conv_01#1 (la domanda sulle forbici ora cerca davvero), conv_20#2 e conv_17#4; rotti
conv_06#2, conv_17#2 e conv_19#2. I tre turni di conv_16 continuano a mancare
`search_knowledge_base`: ora escalano senza cercare, cioè la Regola 2 ha funzionato e la
riga sul grounding no.

### Quanto di tutto questo è merito del prompt

Una parte del movimento **non** dipende dall'intervento. OpenRouter smista le richieste fra
fornitori a monte e il pinning non è implementabile attraverso LiteLLM (ADR-030), quindi due
esecuzioni con lo stesso prompt e temperatura 0 possono divergere. In questa fase se n'è già
visto un caso pulito: nello smoke run conv_01#1 ha cercato nella knowledge base, nella prima
esecuzione completa lo stesso turno non ha cercato affatto, **a prompt identico**.

Il segnale che distingue i due effetti è la **direzione**. I cinque turni corretti sono
esattamente quelli che l'intervento prendeva di mira — i criteri di escalation obbligatori —
e si muovono tutti dalla stessa parte: è difficile attribuirlo al caso. conv_06#2 e conv_17#2
invece sono peggiorati *nel senso contrario* alla modifica: la riga «cercare viene prima di
affermare» può solo aumentare le ricerche, e quei due turni hanno smesso di cercare. Quello
è rumore del fornitore, non un effetto del prompt.

### Il difetto che resta, e perché non lo tocco adesso

conv_09#1 sbaglia ancora, e nel modo peggiore: alla domanda «ho ricevuto una bustina di semi
dieci giorni fa, posso ancora restituirla?» l'agente **cerca** nella knowledge base (progresso
rispetto a prima) e poi apre comunque il ticket ESC-0001, rispondendo soltanto che la
richiesta è stata presa in carico. La Regola 1 è scritta e non ha morso. Nota di contorno: la
`confidence` risultante è `low`, quindi il sistema dichiara da sé di non essere sicuro — il
cap deterministico fa il suo lavoro anche quando il modello sbaglia.

Una seconda iterazione sul prompt è l'ipotesi naturale, ma la fase 7 chiede **un** intervento
misurato e lo ha prodotto. Accumulare modifiche sullo stesso prompt eseguendo l'evaluation
dopo ognuna costa una esecuzione completa per tentativo e, soprattutto, rischia di diventare
sovradattamento a venti conversazioni: a quel punto i numeri salgono e misurano sempre meno.

### Verdetto

L'intervento si **accetta**: la metrica primaria dichiarata prima di eseguirlo sale di 9,3
punti, la secondaria la segue, e i casi corretti sono quelli che il cambiamento prendeva di
mira. Si accetta **con due costi dichiarati**: una regressione su conv_19#2 e un calo di
0.024 su `answer_relevancy` dovuto a risposte che diventano procedura invece di contenuto.
