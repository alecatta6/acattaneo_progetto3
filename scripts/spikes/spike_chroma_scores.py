"""Spike 4: what number does Chroma actually return, and do the e5 prefixes matter?

Performs no LLM calls. Answers two questions that SPEC section 6 leaves open:

1. ``similarity_search_with_score`` returns a cosine *distance*; the relevance-score helper
   returns a normalised similarity. Thresholds must be calibrated on one of them, and the
   choice determines how stable those thresholds are across library upgrades.
2. multilingual-e5 requires ``query: `` / ``passage: `` prefixes. Its model card warns that
   omitting them degrades retrieval silently. This measures the gap on real text.
"""

from __future__ import annotations

import inspect
import shutil
import tempfile
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

MODEL_NAME = "intfloat/multilingual-e5-base"

# Throwaway Italian passages in the project's domain. Not knowledge base content.
PASSAGES: list[tuple[str, str]] = [
    (
        "bulbi",
        "I bulbi di tulipano si piantano in autunno, da ottobre a novembre, a una "
        "profondita' di circa tre volte l'altezza del bulbo. Il terreno deve essere "
        "ben drenato per evitare marciumi.",
    ),
    (
        "resi",
        "I prodotti deperibili come sementi e bulbi non sono rimborsabili dopo "
        "quattordici giorni dalla consegna. Gli attrezzi seguono la garanzia ordinaria "
        "di ventiquattro mesi.",
    ),
    (
        "concime",
        "Il concime granulare per prato va distribuito in dose di trenta grammi per "
        "metro quadro, due volte l'anno, in primavera e a fine estate.",
    ),
    (
        "vasi",
        "I vasi in terracotta trattengono meno umidita' dei vasi in plastica e sono "
        "indicati per piante che temono i ristagni idrici.",
    ),
]

RELEVANT_QUERIES = [
    ("Quando si piantano i bulbi di tulipano?", "bulbi"),
    ("Posso restituire delle sementi dopo tre settimane?", "resi"),
    ("Quanto concime devo usare sul prato?", "concime"),
]

OFF_TOPIC_QUERIES = [
    "Qual e' la capitale del Giappone?",
    "Come si configura un router wifi?",
]


def _build_store(directory: Path, embeddings: HuggingFaceEmbeddings, *, prefixed: bool) -> Chroma:
    """Index the throwaway passages into a fresh Chroma collection.

    Args:
        directory: Where the collection is persisted.
        embeddings: The embedding backend.
        prefixed: Whether to prepend the e5 ``passage: `` prefix to each document.

    Returns:
        The populated Chroma store.
    """
    docs = [
        Document(
            page_content=f"passage: {text}" if prefixed else text,
            metadata={"doc_id": f"{name}.md"},
        )
        for name, text in PASSAGES
    ]
    store = Chroma(
        collection_name="prefixed" if prefixed else "plain",
        embedding_function=embeddings,
        persist_directory=str(directory),
        collection_metadata={"hnsw:space": "cosine"},
    )
    store.add_documents(docs)
    return store


def _probe(store: Chroma, query: str, *, prefixed: bool) -> list[tuple[str, float, float]]:
    """Run one query through both scoring APIs.

    Args:
        store: The Chroma store to query.
        query: The user question.
        prefixed: Whether to prepend the e5 ``query: `` prefix.

    Returns:
        A list of ``(doc_id, raw_score, relevance_score)`` ordered by rank.
    """
    text = f"query: {query}" if prefixed else query
    raw = store.similarity_search_with_score(text, k=len(PASSAGES))
    rel = store.similarity_search_with_relevance_scores(text, k=len(PASSAGES))
    rel_by_id = {d.metadata["doc_id"]: s for d, s in rel}
    return [(d.metadata["doc_id"], s, rel_by_id[d.metadata["doc_id"]]) for d, s in raw]


def main() -> None:
    """Run the spike and print the comparison tables."""
    print("== HuggingFaceEmbeddings signature ==")
    print(" ", inspect.signature(HuggingFaceEmbeddings.__init__))

    print("\n== Chroma scoring API signatures ==")
    for name in ("similarity_search_with_score", "similarity_search_with_relevance_scores"):
        print(f"  {name}{inspect.signature(getattr(Chroma, name))}")

    print(f"\nLoading {MODEL_NAME} (first run downloads ~1.1 GB)...")
    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_NAME,
        encode_kwargs={"normalize_embeddings": True},
    )
    print("loaded.\n")

    tmp = Path(tempfile.mkdtemp(prefix="gt_spike_"))
    try:
        for prefixed in (True, False):
            label = "WITH e5 prefixes" if prefixed else "WITHOUT e5 prefixes"
            store = _build_store(tmp / ("p" if prefixed else "n"), embeddings, prefixed=prefixed)

            print(f"===== {label} =====")
            print(
                f"{'query':<46} {'top1':<11} {'hit':<5} {'raw':<8} {'relevance':<10} {'raw#2':<8}"
            )
            hits = 0
            top_raw_relevant: list[float] = []
            for query, expected in RELEVANT_QUERIES:
                ranked = _probe(store, query, prefixed=prefixed)
                top_id, top_raw, top_rel = ranked[0]
                hit = top_id == f"{expected}.md"
                hits += hit
                top_raw_relevant.append(top_raw)
                print(
                    f"{query[:44]:<46} {top_id:<11} {'YES' if hit else 'no':<5} "
                    f"{top_raw:<8.4f} {top_rel:<10.4f} {ranked[1][1]:<8.4f}"
                )

            top_raw_off: list[float] = []
            for query in OFF_TOPIC_QUERIES:
                ranked = _probe(store, query, prefixed=prefixed)
                top_id, top_raw, top_rel = ranked[0]
                top_raw_off.append(top_raw)
                print(
                    f"{('[fuori tema] ' + query)[:44]:<46} {top_id:<11} {'-':<5} "
                    f"{top_raw:<8.4f} {top_rel:<10.4f} {ranked[1][1]:<8.4f}"
                )

            best_relevant = max(top_raw_relevant)  # worst pertinent case (distance: higher = worse)
            best_off = min(top_raw_off)  # best off-topic case
            print(f"  hit@1 = {hits}/{len(RELEVANT_QUERIES)}")
            print(f"  peggior distanza pertinente = {best_relevant:.4f}")
            print(f"  miglior distanza fuori tema = {best_off:.4f}")
            print(
                f"  SEPARAZIONE = {best_off - best_relevant:+.4f} "
                f"({'separabile' if best_off > best_relevant else 'NON separabile'})\n"
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
