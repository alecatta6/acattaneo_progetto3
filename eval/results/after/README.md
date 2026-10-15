# Seconda esecuzione

Risultati **dopo** l'intervento sul system prompt (ADR-071) e **prima** dell'allungamento
delle conversazioni `memory` (ADR-072), su 43 turni. È lo stato su cui si legge il confronto
prima/dopo dell'intervento: `../before/` è la prima esecuzione, a prompt vecchio e stesso
dataset.

I file nella cartella superiore sono lo stato corrente, su 50 turni, e non sono confrontabili
turno per turno con questi due: due conversazioni hanno più turni, quindi i denominatori
delle metriche sono cambiati.

Commit della seconda esecuzione: `4e41cda`.

**Le trace di questa esecuzione non ci sono.** `eval/results/traces.jsonl` era elencato in
`.gitignore` fra gli artefatti rigenerabili, quindi non è mai stato committato, ed è stato
sovrascritto dalla riesecuzione parziale delle conversazioni `memory`. È esattamente il danno
che quella regola poteva causare, e il motivo per cui è stata rimossa (ADR-073): una trace
non si rigenera, si ripaga a ~300 chiamate e viene diversa (ADR-030). I punteggi di questa
esecuzione restano completi, le risposte turno per turno no.
