"""Measure what the e5 query/passage prefixes actually buy on this corpus.

The e5 model card warns that omitting the prefixes makes retrieval quality "collapse
silently".
That claim is measurable, and a measurement cited in DECISIONS.md should be reproducible,
which is why this lives in the repository rather than in a throwaway file.

The ablation builds a second, temporary index without the prefixes and runs the same probe
set as `probe_retrieval.py`, so the two arms differ in exactly one thing.

Run with: uv run python scripts/ablation_e5_prefixes.py
"""

from __future__ import annotations

import pathlib
import shutil
import statistics
import tempfile

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

from greenthumb.config import get_settings
from greenthumb.kb_loader import load_knowledge_base
from greenthumb.retrieval import chunk_knowledge_base, open_index, search
from probe_retrieval import OFF_TOPIC, RELEVANT  # type: ignore[import-not-found]

TOP_K = 4


class UnprefixedEmbeddings(Embeddings):
    """The same model as production, without the asymmetric e5 prefixes."""

    def __init__(self, model_name: str) -> None:
        """Build the wrapper.

        Args:
            model_name: HuggingFace model identifier.
        """
        self._inner = HuggingFaceEmbeddings(
            model_name=model_name, encode_kwargs={"normalize_embeddings": True}
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents verbatim.

        Args:
            texts: Document texts.

        Returns:
            Embedding vectors.
        """
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a query verbatim.

        Args:
            text: Query text.

        Returns:
            Embedding vector.
        """
        return self._inner.embed_query(text)


def _score_arm(search_fn) -> tuple[int, int, list[float], list[float]]:  # noqa: ANN001
    """Run the probe set through one retrieval arm.

    Args:
        search_fn: Callable taking a query and returning ranked ``(doc_id, similarity)``.

    Returns:
        Hits at rank one, hits within the top four, top-1 similarities for the relevant
        queries, and top-1 similarities for the off-topic ones.
    """
    hits_at_1 = hits_at_4 = 0
    relevant_top: list[float] = []
    for probe in RELEVANT:
        ranked = search_fn(probe.query)
        ids = [doc_id for doc_id, _ in ranked]
        hits_at_1 += ids[0] in probe.acceptable
        hits_at_4 += any(doc_id in probe.acceptable for doc_id in ids)
        relevant_top.append(ranked[0][1])
    off_top = [search_fn(query)[0][1] for query in OFF_TOPIC]
    return hits_at_1, hits_at_4, relevant_top, off_top


def _report(label: str, arm: tuple[int, int, list[float], list[float]]) -> None:
    """Print one arm's results.

    Args:
        label: Human-readable name of the arm.
        arm: The tuple returned by :func:`_score_arm`.
    """
    hits_at_1, hits_at_4, relevant_top, off_top = arm
    total = len(RELEVANT)
    worst_relevant = min(relevant_top)
    best_off_topic = max(off_top)
    print(f"{label}")
    print(f"  hit@1 = {hits_at_1}/{total}   hit@4 = {hits_at_4}/{total}")
    print(f"  pertinenti: min {worst_relevant:.4f}  media {statistics.mean(relevant_top):.4f}")
    print(f"  fuori tema: max {best_off_topic:.4f}  media {statistics.mean(off_top):.4f}")
    print(f"  SEPARAZIONE = {worst_relevant - best_off_topic:+.4f}\n")


def main() -> int:
    """Run both arms and print the comparison.

    Returns:
        0 on success.
    """
    settings = get_settings()

    production = open_index(settings.vector_store_dir, settings.embedding_model)

    def with_prefixes(query: str) -> list[tuple[str, float]]:
        """Query the production index, which applies the prefixes.

        Args:
            query: The probe query.

        Returns:
            Ranked document identifiers with their similarities.
        """
        return [(hit.doc_id, hit.similarity) for hit in search(production, query, TOP_K)]

    chunks = chunk_knowledge_base(load_knowledge_base(settings.kb_dir))
    temporary = pathlib.Path(tempfile.mkdtemp(prefix="gt_ablation_"))
    try:
        plain = Chroma(
            collection_name="ablation_plain",
            embedding_function=UnprefixedEmbeddings(settings.embedding_model),
            persist_directory=str(temporary),
            collection_metadata={"hnsw:space": "cosine"},
        )
        plain.add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])

        def without_prefixes(query: str) -> list[tuple[str, float]]:
            """Query the temporary index, which applies no prefixes.

            Args:
                query: The probe query.

            Returns:
                Ranked document identifiers with their similarities.
            """
            results = plain.similarity_search_with_score(query, k=TOP_K)
            return [(d.metadata["doc_id"], round(1.0 - dist, 4)) for d, dist in results]

        print(f"Ablazione sui prefissi e5 — {len(chunks)} chunk\n")
        _report("CON prefissi (indice di produzione)", _score_arm(with_prefixes))
        _report("SENZA prefissi (indice temporaneo)", _score_arm(without_prefixes))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
