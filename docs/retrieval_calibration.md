# Calibrazione del retrieval — fase 2

Prodotto da `scripts/probe_retrieval.py` sulla knowledge base di 37 documenti (207 chunk),
modello `intfloat/multilingual-e5-base`, `top_k = 4`, metrica coseno.

Gli score riportati sono **similarità**, calcolate da noi come `1 − distanza` a partire da
`similarity_search_with_score` (ADR-021).

## Query pertinenti (12)

Formulate come le scriverebbe un cliente, **senza riusare le frasi dei documenti** che
dovrebbero recuperare: interrogare con le parole del documento gonfierebbe gli score e
calibrerebbe le soglie su una situazione che in produzione non si verifica mai.

| Query | Top-1 | Similarità | hit@1 |
|---|---|---|---|
| Posso piantare adesso i bulbi di tulipano? | products/bulbi_tulipano_triumph.md | 0.8511 | sì |
| Entro quanto tempo posso restituire delle sementi? | policies/resi_rimborsi.md | 0.8873 | sì |
| Quanto costa la spedizione e quando arriva il pacco? | policies/spedizioni.md | 0.8697 | sì |
| Il pacco è arrivato schiacciato, cosa devo fare? | policies/danni_trasporto.md | 0.8762 | sì |
| Le forbici si sono rotte dopo un mese, sono coperte? | policies/garanzia_attrezzi.md | 0.8491 | sì |
| Posso pagare alla consegna in contanti? | policies/pagamenti.md | 0.8578 | sì |
| A che ora posso chiamarvi il sabato? | policies/contatti_orari.md | 0.8432 | sì |
| Quanto concime devo mettere sul prato per metro quadro? | products/concime_granulare_prato_5kg.md | 0.8793 | sì |
| Le foglie della mia pianta stanno diventando gialle, perché? | guides/foglie_ingialliscono.md | 0.8821 | sì |
| A che profondità vanno interrati i narcisi? | products/bulbi_narciso_tete_a_tete.md | 0.8195 | sì |
| Ho un balcone con poche ore di sole, cosa riesco a coltivare? | guides/coltivare_in_balcone.md | 0.8796 | sì |
| Come si diluisce il concime liquido per i gerani? | products/concime_liquido_fiorite_1l.md | 0.8557 | sì |

**hit@1 = 12/12 (100%) — hit@4 = 12/12 (100%)**, contro un obiettivo di fase 2 di hit@4 ≥ 90%.

## Query fuori tema (8)

| Query | Top-1 recuperato | Similarità |
|---|---|---|
| Qual è la capitale del Giappone? | guides/concimazione_quando_e_quanto.md | 0.7433 |
| Come si configura un router wifi? | guides/annaffiatura_corretta.md | 0.7926 |
| Quanto costa un volo per New York? | policies/spedizioni.md | 0.7915 |
| Chi ha vinto il campionato di calcio quest'anno? | policies/danni_trasporto.md | 0.7346 |
| Come si cambia una gomma dell'automobile? | products/forbici_potatura_bypass.md | 0.8031 |
| Mi serve un mutuo per comprare casa | policies/garanzia_attrezzi.md | 0.8063 |
| Come si scrive un ciclo for in Python? | guides/concimazione_quando_e_quanto.md | 0.8009 |
| Qual è l'orario dei treni per Milano? | policies/spedizioni.md | 0.8029 |

Si noti che il retrieval restituisce **sempre** qualcosa: è la soglia, non il motore, a dover
stabilire che nessun documento è davvero pertinente.

## Distribuzione

| Gruppo | min | media | mediana | max |
|---|---|---|---|---|
| Pertinenti (top-1) | 0.8195 | 0.8626 | 0.8638 | 0.8873 |
| Fuori tema (top-1) | 0.7346 | 0.7844 | 0.7967 | 0.8063 |

- Peggior pertinente: **0.8195**
- Miglior fuori tema: **0.8063**
- **Separazione: +0.0132**

## Soglie scelte

| Parametro | Valore | Criterio |
|---|---|---|
| `GREENTHUMB_RETRIEVAL_SCORE_LOW` | **0.813** | punto medio fra i due gruppi, massimo margine su entrambi i lati |
| `GREENTHUMB_RETRIEVAL_SCORE_HIGH` | **0.864** | mediana dei pertinenti: circa metà dei recuperi validi può dichiarare confidence alta |

## Ablazione sui prefissi e5

CLAUDE.md avverte che senza i prefissi `query: ` / `passage: ` «la qualità del retrieval crolla
in modo silenzioso». Misurato sulla knowledge base reale:

| | hit@1 | hit@4 | Peggior pertinente | Miglior fuori tema | Separazione |
|---|---|---|---|---|---|
| **Con** prefissi | **12/12** | 12/12 | 0.8195 | 0.8063 | **+0.0132** |
| **Senza** prefissi | 11/12 | 12/12 | 0.8268 | 0.8139 | +0.0130 |

I prefissi recuperano una query in prima posizione e lasciano la separazione invariata. Il
crollo descritto non si verifica su questo corpus. Si mantengono comunque: sono l'uso
documentato del modello, non costano nulla e il miglioramento su hit@1 è reale.

## Limiti di questa calibrazione

La separazione di 0.0132 è **molto stretta**: con soglia a 0.813 restano circa 0.0065 di margine
per lato. Le soglie sono inoltre stimate su sole 20 query. Non vanno considerate un confine
affidabile, ma un segnale fra i tre che il sistema usa:

1. il system prompt istruisce l'agente a rifiutare le domande fuori ambito (SPEC §8);
2. la soglia bassa dichiara «nessun documento rilevante»;
3. le stesse similarità limitano la `confidence`, quindi un recupero borderline produce
   comunque una risposta dichiaratamente incerta.

La fase 7 rivaluta le soglie su 20 conversazioni indipendenti da queste query, ed è la sede
prevista per l'intervento correttivo misurato.
