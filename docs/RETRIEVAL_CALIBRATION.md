# Calibrazione del retrieval — fase 2

Prodotto da `scripts/probe_retrieval.py` sulla knowledge base di 37 documenti, modello
`intfloat/multilingual-e5-base`, `top_k = 4`, metrica coseno.

Gli score sono **similarità**, calcolate da noi come `1 − distanza` a partire da
`similarity_search_with_score` (ADR-021).

> **Seconda calibrazione.** La prima era stata eseguita su un chunking che ripeteva il titolo
> del documento fino a tre volte in ogni chunk. Corretto quel difetto (ADR-045), l'indice è
> stato ricostruito e tutte le misure rifatte. I numeri sotto sono quelli validi; quelli della
> prima calibrazione compaiono solo nei confronti, dichiarati come tali.

## Query pertinenti (12)

Formulate come le scriverebbe un cliente, **senza riusare le frasi dei documenti** che
dovrebbero recuperare: interrogare con le parole del documento gonfierebbe gli score e
calibrerebbe le soglie su una situazione che in produzione non si verifica mai.

| Query | Top-1 | Similarità | hit@1 |
|---|---|---|---|
| Posso piantare adesso i bulbi di tulipano? | products/bulbi_tulipano_triumph.md | 0.8534 | sì |
| Entro quanto tempo posso restituire delle sementi? | policies/resi_rimborsi.md | 0.8842 | sì |
| Quanto costa la spedizione e quando arriva il pacco? | policies/spedizioni.md | 0.8692 | sì |
| Il pacco è arrivato schiacciato, cosa devo fare? | policies/danni_trasporto.md | 0.8793 | sì |
| Le forbici si sono rotte dopo un mese, sono coperte? | policies/garanzia_attrezzi.md | 0.8507 | sì |
| Posso pagare alla consegna in contanti? | policies/pagamenti.md | 0.8574 | sì |
| A che ora posso chiamarvi il sabato? | policies/contatti_orari.md | 0.8464 | sì |
| Quanto concime devo mettere sul prato per metro quadro? | products/concime_granulare_prato_5kg.md | 0.8834 | sì |
| Le foglie della mia pianta stanno diventando gialle, perché? | guides/foglie_ingialliscono.md | 0.8799 | sì |
| A che profondità vanno interrati i narcisi? | products/trapiantatoio_acciaio_inox.md | 0.8185 | **no** |
| Ho un balcone con poche ore di sole, cosa riesco a coltivare? | guides/coltivare_in_balcone.md | 0.8797 | sì |
| Come si diluisce il concime liquido per i gerani? | products/concime_liquido_fiorite_1l.md | 0.8554 | sì |

**hit@1 = 11/12 (92%) — hit@4 = 12/12 (100%)**, contro un obiettivo di fase 2 di hit@4 ≥ 90%.

### L'unico hit@1 mancato

La query sui narcisi produce un pareggio praticamente perfetto:

| Similarità | Documento |
|---|---|
| 0.8185 | products/trapiantatoio_acciaio_inox.md |
| 0.8182 | products/bulbi_narciso_tete_a_tete.md |
| 0.8181 | products/substrato_bulbi_20l.md |

I primi tre distano **0.0004**, e tutti e tre rispondono davvero alla domanda: la scheda del
trapiantatoio contiene la sezione sulla lama graduata, che riporta «per i narcisi nani 10-12 cm».
Il documento atteso è secondo per quattro decimillesimi. Si registra comunque come hit@1 mancato:
allargare a posteriori l'insieme dei documenti accettabili per far tornare una metrica è il modo
più rapido di rendere un benchmark inutile.

## Query fuori tema (8)

| Query | Top-1 recuperato | Similarità |
|---|---|---|
| Qual è la capitale del Giappone? | guides/concimazione_quando_e_quanto.md | 0.7462 |
| Come si configura un router wifi? | guides/annaffiatura_corretta.md | 0.7915 |
| Quanto costa un volo per New York? | policies/spedizioni.md | 0.7921 |
| Chi ha vinto il campionato di calcio quest'anno? | guides/potatura_arbusti_quando.md | 0.7337 |
| Come si cambia una gomma dell'automobile? | products/forbici_potatura_bypass.md | 0.8008 |
| Mi serve un mutuo per comprare casa | policies/garanzia_attrezzi.md | 0.8082 |
| Come si scrive un ciclo for in Python? | guides/concimazione_quando_e_quanto.md | 0.8028 |
| Qual è l'orario dei treni per Milano? | policies/contatti_orari.md | 0.8066 |

Il retrieval restituisce **sempre** qualcosa: è la soglia, non il motore, a dover stabilire che
nessun documento è davvero pertinente.

## Distribuzione

| Gruppo | min | media | mediana | max |
|---|---|---|---|---|
| Pertinenti (top-1) | 0.8185 | 0.8631 | 0.8633 | 0.8842 |
| Fuori tema (top-1) | 0.7337 | 0.7852 | 0.7964 | 0.8082 |

- Peggior pertinente: **0.8185**
- Miglior fuori tema: **0.8082**
- **Separazione: +0.0103**

## Soglie scelte

| Parametro | Valore | Criterio |
|---|---|---|
| `GREENTHUMB_RETRIEVAL_SCORE_LOW` | **0.813** | punto medio fra i due gruppi, massimo margine su entrambi i lati |
| `GREENTHUMB_RETRIEVAL_SCORE_HIGH` | **0.863** | mediana dei pertinenti: circa metà dei recuperi validi può dichiarare confidence alta |

## Effetto del chunking pulito

Confronto fra la prima calibrazione (titolo ripetuto fino a tre volte per chunk) e la seconda
(ADR-045), a parità di tutto il resto:

| Chunking | Chunk | Caratteri medi | hit@1 | hit@4 | Separazione |
|---|---|---|---|---|---|
| Ridondante | 207 | 546 | 12/12 | 12/12 | +0.0132 |
| **Pulito** | 206 | 519 | 11/12 | 12/12 | +0.0103 |

Il chunking pulito **non migliora** le metriche di retrieval: `hit@1` scende di una query (quella
del pareggio a 0.0004 descritto sopra) e la separazione si restringe di 0.0029. Il guadagno è
altrove: 5% di caratteri in meno per chunk, e soprattutto l'eliminazione di una ripetizione che
il modello leggeva a ogni turno senza ricavarne nulla.

## Ablazione sui prefissi e5

Prodotta da `scripts/ablation_e5_prefixes.py` sullo stesso indice e sulle stesse query.

| Chunking | Prefissi | hit@1 | hit@4 | Separazione min/max | Distanza fra le medie |
|---|---|---|---|---|---|
| Ridondante | con | 12/12 | 12/12 | +0.0132 | 0.0782 |
| Ridondante | senza | 11/12 | 12/12 | +0.0130 | 0.0704 |
| **Pulito** | **con** | 11/12 | 12/12 | +0.0103 | **0.0779** |
| Pulito | senza | 11/12 | 12/12 | **+0.0181** | 0.0701 |

Le due statistiche **si contraddicono**. Sulla separazione fra gli estremi i prefissi risultano
dannosi; sulla distanza fra le medie risultano utili, e di un margine maggiore.

La spiegazione più semplice è che min e max, su 12 e 8 query, sono determinati da **singole
query**, e sono quindi la statistica meno stabile che si possa scegliere. La distanza fra le
medie usa tutte le osservazioni ed è coerente in entrambe le configurazioni di chunking.

Si mantengono i prefissi: sono l'uso documentato del modello, la statistica più stabile li
favorisce, e `hit@1`/`hit@4` sono identici nelle due varianti. Resta però registrato che
l'avvertimento della documentazione e5 — «senza, la qualità del retrieval crolla in modo
silenzioso» — **non
è confermato da nessuna delle quattro misure**.

## Limiti di questa calibrazione

La separazione di 0.0103 è **molto stretta**: con soglia a 0.813 restano circa 0.005 di margine
per lato, stimati su 20 query scritte da chi ha scritto anche la knowledge base. Le soglie non
vanno considerate un confine affidabile, ma un segnale fra i tre che il sistema usa:

1. il system prompt istruisce l'agente a rifiutare le domande fuori ambito (SPEC §8);
2. la soglia bassa dichiara «nessun documento rilevante»;
3. le stesse similarità limitano la `confidence`, quindi un recupero borderline produce
   comunque una risposta dichiaratamente incerta.

La fase 7 rivaluta le soglie su 20 conversazioni indipendenti da queste query, ed è la sede
prevista per l'intervento correttivo misurato.
