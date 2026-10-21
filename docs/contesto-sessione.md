# Contesto per ripartire

Agente ReAct di customer care per un e-commerce fittizio di giardinaggio (progetto d'esame).
**Fasi 0-8 chiuse, fase 9 aperta.** 317 test unitari verdi, 23 marcati `llm` esclusi da
`make test`. Repository pubblico; il deliverable è il link Colab al notebook, che porta gli
output salvati e si legge senza eseguire nulla.

Ordine di lettura: `CONVENTIONS.md` (convenzioni e insidie delle librerie, da leggere prima di
scrivere codice) → `PLAN.md` (stato e DoD per fase) → `SPEC.md` (tracciabilità R1-R10, §1) →
`DECISIONS.md` (76 ADR, il perché di tutto: ogni numero citato qui rimanda là) →
`eval/results/summary.md`. Le due convenzioni meno ovvie: **nomi, docstring e commit in
inglese** mentre **tutto ciò che legge il cliente è in italiano**, e **ogni scelta non ovvia va
in `DECISIONS.md`** con le alternative scartate, perché è la materia prima della relazione.

## Decisioni portanti

- **Deterministico prima del probabilistico**: dei 4 campi della risposta solo `answer` viene
  dall'LLM — rende impossibile una fonte inventata (ADR-002).
- **Data di business simulata** (12/10/2026), perché ordini ed evaluation non invecchino (ADR-003).
- **Summarization, non trimming**: il numero d'ordine del turno 1 serve dieci turni dopo (ADR-004).
- **`confidence` e `needs_human` ortogonali**: la prima qualifica, il secondo instrada (ADR-007).
- **`needs_human` ha semantica di sessione**, non di turno (ADR-008).
- **OpenRouter via LiteLLM**, ma i giudici usano l'endpoint diretto: due forme dello stesso
  identificatore di modello (ADR-029, ADR-033).
- **Trace e punteggi dell'evaluation versionati**: ricalcolare le metriche non deve costare 300
  chiamate (ADR-073).
- **Notebook e `summary.md` sono generati** da script, non scritti a mano (ADR-069, ADR-075).

## Aperto, a metà, o noto e non risolto

- **Fase 9**: il notebook non è mai stato eseguito su Colab, gli output committati sono locali.
  Servono due Secrets, non uno: `OPENAI_API_KEY` **e** `GREENTHUMB_LLM_MODEL` (ADR-076).
- **conv_09#1 sbaglia ancora**: su una domanda di policy coperta dalla KB apre un ticket invece
  di rispondere. Misurato e non corretto (ADR-071).
- **Costo dell'intervento di fase 7**: dove apre un ticket, la risposta tende a diventare *solo*
  il ticket. Prossimo passo: ticket **in aggiunta** alla risposta (ADR-071).
- **`source recall` 54,3%**: circa un terzo dei fallimenti sono aspettative strette del dataset,
  non difetti dell'agente — non è un numero da "sistemare" (ADR-070).
- **`faithfulness` 0.000 su `edge_cases`** è un artefatto: un rifiuto non contiene affermazioni
  da sostenere. Documentato e deliberatamente non corretto (ADR-070).
- **Le trace della seconda esecuzione sono perse** per una vecchia regola di `.gitignore`: i
  punteggi restano, le risposte turno per turno no (ADR-073).
- **Mai provati**: re-ranking e ricerca con diversificazione, ipotesi già formulata (ADR-068).
- **Limite più serio**: nessuna autenticazione del cliente — chi conosce un numero d'ordine ne
  vede i dettagli. Dichiarato, non implementato.

## Da NON toccare senza averne misurato l'effetto

- **Soglie 0.813 / 0.863**: calibrate, separazione di soli +0.0132 (`RETRIEVAL_CALIBRATION.md`).
  Una soglia a 0 disattiva il filtro **in silenzio** (ADR-043).
- **`summary_trigger_tokens` 6000**: sotto il pavimento di ~2583 la summarization scatta a ogni
  chiamata, e i test diventerebbero *più* verdi, non meno (ADR-056, ADR-072).
- **Il `config: RunnableConfig` del tool di escalation non ha default, di proposito**: aggiungerlo
  disattiva l'iniezione senza errori e unisce tutte le sessioni (ADR-047).
- **`langchain-community==0.3.31`**: pin fragile ma necessario, senza cui `import ragas` muore (ADR-019).
- **`expected_sources` del dataset**: non allargarli per far salire le metriche (ADR-045).
- **Notebook e `summary.md`**: modificarli a mano funziona una volta, poi la rigenerazione
  cancella tutto. Si modificano i generatori.
- **Il `.env` locale**: un valore copiato e dimenticato vince sui default calibrati. È già
  costato tre volte (ADR-043, ADR-072).
