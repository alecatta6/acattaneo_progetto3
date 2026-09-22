"""Tests for the knowledge base search tool.

The tool is exercised against a fake store rather than the real index: the threshold
logic, the formatting and the artifact are pure behaviour, and testing them must not
require a 1.1 GB model download or a built index. One test does hit the real index, and
skips when it is absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_core.tools import StructuredTool

from greenthumb.config import get_settings
from greenthumb.tools.knowledge_base_tool import TOOL_NAME, make_knowledge_base_tool

LOW = 0.813
TOP_K = 4


@dataclass
class _FakeStore:
    """Stands in for Chroma, returning canned results with chosen distances.

    Attributes:
        hits: Tuples of ``(doc_id, chunk_index, similarity)`` to return.
        last_filter: The filter passed by the last call, for assertions.
    """

    hits: list[tuple[str, int, float]]
    last_filter: dict[str, str] | None = None

    def similarity_search_with_score(
        self, query: str, k: int = 4, filter: dict[str, str] | None = None, **kwargs: Any
    ) -> list[tuple[Document, float]]:
        """Return the canned hits as Chroma would, as (document, distance) pairs.

        Args:
            query: The query text, ignored.
            k: How many results to return.
            filter: The metadata filter, recorded for assertions.
            **kwargs: Ignored.

        Returns:
            Document and cosine-distance pairs.
        """
        self.last_filter = filter
        results = []
        for doc_id, index, similarity in self.hits[:k]:
            document = Document(
                page_content=f"Contenuto del chunk {index} di {doc_id}",
                metadata={
                    "doc_id": doc_id,
                    "title": f"Titolo di {doc_id}",
                    "doc_type": doc_id.split("/")[0].rstrip("s"),
                    "chunk_id": f"{doc_id}#{index}",
                },
            )
            results.append((document, 1.0 - similarity))
        return results


def _tool(hits: list[tuple[str, int, float]]) -> tuple[StructuredTool, _FakeStore]:
    """Build the tool over a fake store.

    Args:
        hits: The canned hits the store should return.

    Returns:
        The tool and the store it queries.
    """
    store = _FakeStore(hits=hits)
    return make_knowledge_base_tool(store, TOP_K, LOW), store


# --- contract -------------------------------------------------------------------------


def test_tool_declares_the_artifact_response_format() -> None:
    """response.py reads artifacts from ToolMessages, which requires this format."""
    tool, _ = _tool([])
    assert tool.name == TOOL_NAME
    assert tool.response_format == "content_and_artifact"


def test_description_steers_the_model() -> None:
    """SPEC 7 requires the description to say when not to use the tool, and to reformulate."""
    tool, _ = _tool([])
    assert "NON USARLO" in tool.description
    assert "get_order_status" in tool.description
    assert "Riformula" in tool.description


# --- threshold ------------------------------------------------------------------------


def test_results_below_the_threshold_are_withheld_from_the_model() -> None:
    """The model must never see chunks the system considers irrelevant (ADR-040)."""
    tool, _ = _tool([("guides/a.md", 0, 0.90), ("guides/b.md", 0, 0.70)])
    content, artifact = tool.func(query="una domanda")
    assert "guides/a.md" in content
    assert "guides/b.md" not in content
    assert [r["doc_id"] for r in artifact["results"]] == ["guides/a.md"]


def test_nothing_above_threshold_yields_an_explicit_refusal() -> None:
    """Off-topic questions still retrieve something; the threshold must reject it."""
    tool, _ = _tool([("guides/concimazione.md", 0, 0.74)])
    content, artifact = tool.func(query="Qual e' la capitale del Giappone?")
    flat = " ".join(content.split())  # the message wraps at 100 columns
    assert artifact["results"] == []
    assert "Nessun documento rilevante" in flat
    assert "NON rispondere basandoti su conoscenza generale" in flat


def test_no_results_message_distinguishes_escalation_from_refusal() -> None:
    """A gap in the knowledge base and an out-of-scope question need different handling."""
    tool, _ = _tool([("guides/x.md", 0, 0.50)])
    content, _ = tool.func(query="qualcosa")
    flat = " ".join(content.split())
    assert "no_knowledge" in flat
    assert "fuori ambito, rifiuta cortesemente" in flat


def test_best_similarity_is_recorded_even_when_nothing_passes() -> None:
    """The confidence cap must tell "ran and found nothing" from "never ran" (SPEC 5)."""
    tool, _ = _tool([("guides/x.md", 0, 0.74)])
    _, artifact = tool.func(query="domanda")
    assert artifact["best_similarity"] == pytest.approx(0.74)
    assert artifact["threshold"] == LOW


def test_boundary_value_is_inclusive() -> None:
    """A hit exactly at the threshold counts as relevant, matching the documented rule."""
    tool, _ = _tool([("guides/a.md", 0, LOW)])
    _, artifact = tool.func(query="domanda")
    assert len(artifact["results"]) == 1


# --- artifact -------------------------------------------------------------------------


def test_artifact_carries_doc_id_score_and_chunk_id() -> None:
    """SPEC 7 fixes these three fields; response.py depends on all of them."""
    tool, _ = _tool([("guides/a.md", 2, 0.90)])
    _, artifact = tool.func(query="domanda")
    entry = artifact["results"][0]
    assert entry["doc_id"] == "guides/a.md"
    assert entry["score"] == 0.90
    assert entry["chunk_id"] == "guides/a.md#2"


def test_several_chunks_of_one_document_are_kept_separate() -> None:
    """Deduplication belongs to response.py, which needs the chunk-level detail."""
    tool, _ = _tool([("guides/a.md", 0, 0.90), ("guides/a.md", 3, 0.87)])
    _, artifact = tool.func(query="domanda")
    assert len(artifact["results"]) == 2
    assert {r["chunk_id"] for r in artifact["results"]} == {"guides/a.md#0", "guides/a.md#3"}


# --- filtering and input handling -----------------------------------------------------


def test_doc_type_filter_reaches_the_store() -> None:
    """The filter must be applied by the store, not simulated afterwards."""
    tool, store = _tool([("policies/resi.md", 0, 0.90)])
    _, artifact = tool.func(query="resi", doc_type="policy")
    assert store.last_filter == {"doc_type": "policy"}
    assert artifact["doc_type"] == "policy"


def test_absent_filter_searches_everything() -> None:
    """Leaving the filter out must not silently restrict the search."""
    tool, store = _tool([("guides/a.md", 0, 0.90)])
    tool.func(query="domanda")
    assert store.last_filter is None


@pytest.mark.parametrize("query", ["", "   ", "\n"])
def test_empty_query_is_answered_not_raised(query: str) -> None:
    """A raising tool breaks the turn; an empty query deserves a readable answer.

    Args:
        query: An empty or whitespace-only query.
    """
    tool, _ = _tool([("guides/a.md", 0, 0.90)])
    content, artifact = tool.func(query=query)
    assert "query di ricerca e' vuota" in content
    assert artifact["results"] == []


def test_query_is_trimmed_before_use() -> None:
    """Stray whitespace must not reach the artifact and skew later comparisons."""
    tool, _ = _tool([("guides/a.md", 0, 0.90)])
    _, artifact = tool.func(query="  bulbi autunnali  ")
    assert artifact["query"] == "bulbi autunnali"


# --- against the real index -----------------------------------------------------------


def test_real_index_answers_the_assignment_question() -> None:
    """End to end on the built index, skipped when the index has not been built."""
    settings = get_settings()
    if not settings.vector_store_dir.exists():
        pytest.skip("indice non costruito: eseguire `make index`")

    from greenthumb.retrieval import open_index

    store = open_index(settings.vector_store_dir, settings.embedding_model)
    tool = make_knowledge_base_tool(store, settings.retrieval_top_k, LOW)

    _, artifact = tool.func(query="Quando si piantano i bulbi di tulipano?")
    assert "guides/bulbi_autunnali.md" in {r["doc_id"] for r in artifact["results"]}

    _, off_topic = tool.func(query="Qual e' la capitale del Giappone?")
    assert off_topic["results"] == [], "la soglia non sta filtrando le domande fuori tema"


def test_artifact_carries_the_chunk_text_for_the_evaluation() -> None:
    """RAGAS scores faithfulness against the contexts, so they travel structured (ADR-059)."""
    tool, _ = _tool([("guides/a.md", 0, 0.90)])
    _, artifact = tool.func(query="domanda")
    entry = artifact["results"][0]
    assert "text" in entry
    assert entry["text"], "il testo del chunk non deve essere vuoto"
