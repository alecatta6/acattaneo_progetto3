"""Calibrate the retrieval thresholds on real data.

CLAUDE.md warns that e5 scores cluster in a high, narrow band and must be calibrated
empirically rather than guessed. This script runs a fixed probe set — queries phrased the
way a customer would ask, plus deliberately off-topic ones — and reports the score
distribution of each group, from which the two thresholds follow.

The relevant queries deliberately avoid copying the wording of the documents they should
retrieve: matching a document's own sentences would inflate the scores and calibrate the
thresholds against a situation that never occurs in production.

Run with: uv run python scripts/probe_retrieval.py
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from greenthumb.config import get_settings
from greenthumb.retrieval import open_index, search

TOP_K = 4


@dataclass(frozen=True)
class Probe:
    """One relevant probe query and the documents that may legitimately answer it.

    Attributes:
        query: The question, phrased as a customer would ask it.
        acceptable: Documents any of which counts as a correct retrieval.
    """

    query: str
    acceptable: tuple[str, ...]


RELEVANT: tuple[Probe, ...] = (
    Probe(
        "Posso piantare adesso i bulbi di tulipano?",
        ("guides/bulbi_autunnali.md", "products/bulbi_tulipano_triumph.md"),
    ),
    Probe(
        "Entro quanto tempo posso restituire delle sementi?",
        ("policies/prodotti_deperibili.md", "policies/resi_rimborsi.md"),
    ),
    Probe("Quanto costa la spedizione e quando arriva il pacco?", ("policies/spedizioni.md",)),
    Probe("Il pacco e' arrivato schiacciato, cosa devo fare?", ("policies/danni_trasporto.md",)),
    Probe(
        "Le forbici si sono rotte dopo un mese, sono coperte?", ("policies/garanzia_attrezzi.md",)
    ),
    Probe("Posso pagare alla consegna in contanti?", ("policies/pagamenti.md",)),
    Probe("A che ora posso chiamarvi il sabato?", ("policies/contatti_orari.md",)),
    Probe(
        "Quanto concime devo mettere sul prato per metro quadro?",
        ("products/concime_granulare_prato_5kg.md", "guides/concimazione_quando_e_quanto.md"),
    ),
    Probe(
        "Le foglie della mia pianta stanno diventando gialle, perche'?",
        ("guides/foglie_ingialliscono.md",),
    ),
    Probe(
        "A che profondita' vanno interrati i narcisi?",
        ("products/bulbi_narciso_tete_a_tete.md", "guides/bulbi_autunnali.md"),
    ),
    Probe(
        "Ho un balcone con poche ore di sole, cosa riesco a coltivare?",
        ("guides/giardinaggio_poca_luce.md", "guides/coltivare_in_balcone.md"),
    ),
    Probe(
        "Come si diluisce il concime liquido per i gerani?",
        ("products/concime_liquido_fiorite_1l.md", "guides/concimazione_quando_e_quanto.md"),
    ),
)

OFF_TOPIC: tuple[str, ...] = (
    "Qual e' la capitale del Giappone?",
    "Come si configura un router wifi?",
    "Quanto costa un volo per New York?",
    "Chi ha vinto il campionato di calcio quest'anno?",
    "Come si cambia una gomma dell'automobile?",
    "Mi serve un mutuo per comprare casa",
    "Come si scrive un ciclo for in Python?",
    "Qual e' l'orario dei treni per Milano?",
)


def _short(doc_id: str) -> str:
    """Abbreviate a doc_id so the probe tables stay readable in a terminal.

    Args:
        doc_id: The full document identifier.

    Returns:
        The identifier with its folder abbreviated to a single letter.
    """
    for folder, letter in (("products/", "p/"), ("guides/", "g/"), ("policies/", "P/")):
        doc_id = doc_id.replace(folder, letter)
    return doc_id[:32]


def main() -> int:
    """Run the probe set and print the calibration tables.

    Returns:
        0 when hit@4 meets the phase-2 target, 1 otherwise.
    """
    settings = get_settings()
    store = open_index(settings.vector_store_dir, settings.embedding_model)

    print("=" * 96)
    print("QUERY PERTINENTI")
    print("=" * 96)
    print(f"{'query':<52} {'top-1':<34} {'sim':<7} {'hit@1':<6} hit@4")

    hits_at_1 = 0
    hits_at_4 = 0
    relevant_top: list[float] = []
    misses: list[str] = []

    for probe in RELEVANT:
        results = search(store, probe.query, top_k=TOP_K)
        ids = [hit.doc_id for hit in results]
        at_1 = ids[0] in probe.acceptable
        at_4 = any(doc_id in probe.acceptable for doc_id in ids)
        hits_at_1 += at_1
        hits_at_4 += at_4
        relevant_top.append(results[0].similarity)
        if not at_4:
            misses.append(f"{probe.query}  ->  atteso {probe.acceptable}, ottenuto {ids}")
        print(
            f"{probe.query[:50]:<52} {_short(ids[0]):<34} "
            f"{results[0].similarity:<7.4f} {'SI' if at_1 else 'no':<6} {'SI' if at_4 else 'NO'}"
        )

    print("\n" + "=" * 96)
    print("QUERY FUORI TEMA (non devono superare la soglia bassa)")
    print("=" * 96)
    print(f"{'query':<52} {'top-1':<34} {'sim':<7}")

    off_top: list[float] = []
    for query in OFF_TOPIC:
        results = search(store, query, top_k=TOP_K)
        off_top.append(results[0].similarity)
        print(f"{query[:50]:<52} {_short(results[0].doc_id):<34} {results[0].similarity:<7.4f}")

    n = len(RELEVANT)
    print("\n" + "=" * 96)
    print("DISTRIBUZIONE")
    print("=" * 96)
    print(f"  hit@1 = {hits_at_1}/{n} ({hits_at_1 / n:.0%})")
    print(f"  hit@4 = {hits_at_4}/{n} ({hits_at_4 / n:.0%})    [obiettivo fase 2: >= 90%]")
    print()
    print(f"{'gruppo':<14} {'min':<9} {'media':<9} {'mediana':<9} {'max':<9}")
    for label, values in (("pertinenti", relevant_top), ("fuori tema", off_top)):
        print(
            f"{label:<14} {min(values):<9.4f} {statistics.mean(values):<9.4f} "
            f"{statistics.median(values):<9.4f} {max(values):<9.4f}"
        )

    worst_relevant = min(relevant_top)
    best_off_topic = max(off_top)
    gap = worst_relevant - best_off_topic
    print()
    print(f"  peggior pertinente  = {worst_relevant:.4f}")
    print(f"  miglior fuori tema  = {best_off_topic:.4f}")
    print(f"  SEPARAZIONE         = {gap:+.4f}  ({'separabile' if gap > 0 else 'SOVRAPPOSTI'})")

    if gap > 0:
        low = round((worst_relevant + best_off_topic) / 2, 3)
        high = round(statistics.median(relevant_top), 3)
        print()
        print("  soglie suggerite (punto medio fra i due gruppi, e mediana dei pertinenti):")
        print(f"    GREENTHUMB_RETRIEVAL_SCORE_LOW  = {low}")
        print(f"    GREENTHUMB_RETRIEVAL_SCORE_HIGH = {high}")

    if misses:
        print("\n  query pertinenti mancate:")
        for miss in misses:
            print(f"    {miss}")

    return 0 if hits_at_4 / n >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
