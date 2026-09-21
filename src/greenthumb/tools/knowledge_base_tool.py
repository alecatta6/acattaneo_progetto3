"""The knowledge base search tool.

This is the only route to product facts, agronomic advice and shop policy: if a statement
is not here, the agent must not make it. Three things follow from that.

**The threshold decides, and it decides here.** Retrieval always returns something — asked
for the capital of Japan it returns the fertiliser guide at 0.74 (ADR-040). One place must
rule on relevance, and it is this tool, so the model never sees chunks we consider
irrelevant.

**Nothing found is a result, not a failure.** The message says so explicitly and tells the
model not to invent and to consider escalation, because a confident wrong answer about a
returns deadline is worse than an admission of ignorance.

**The artifact carries the numbers, not the prose.** ``response.py`` intersects the model's
citations with what retrieval really returned (ADR-002), and needs the scores to cap the
confidence, so both travel as structured data rather than being parsed back out of text.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_chroma import Chroma
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from greenthumb.retrieval import SearchHit, search

TOOL_NAME = "search_knowledge_base"

# Written for the model: it decides on this text alone whether and how to call the tool.
TOOL_DESCRIPTION = """\
Cerca nella knowledge base di GreenThumb: schede prodotto, guide di coltivazione e cura,
policy del negozio (resi, spedizioni, garanzie, pagamenti, contatti).

USALO ogni volta che devi affermare qualcosa su un prodotto, su come coltivare o curare una
pianta, o sulle condizioni commerciali del negozio. Queste informazioni esistono solo qui:
se non le trovi, non affermarle.

NON USARLO per lo stato di un ordine specifico, che si recupera con get_order_status.

Riformula la domanda del cliente in una query di ricerca autonoma e specifica, invece di
copiarla alla lettera: "e quelli che ho comprato?" non e' una query utile. Se la domanda ne
contiene piu' di una, esegui piu' ricerche separate.

Il parametro doc_type restringe la ricerca quando sai gia' che tipo di documento ti serve:
'policy' per resi, spedizioni, garanzie e pagamenti; 'product' per una scheda prodotto;
'guide' per consigli di coltivazione. Lascialo vuoto se non sei sicuro."""

EMPTY_QUERY_MESSAGE = """\
La query di ricerca e' vuota. Formula una domanda specifica su un prodotto, una tecnica di
coltivazione o una policy del negozio, poi riprova."""

NO_RESULTS_MESSAGE = """\
Nessun documento rilevante trovato per: {query!r}{scope}

La knowledge base non contiene informazioni su questo punto. NON rispondere basandoti su
conoscenza generale: le condizioni commerciali, i prezzi e i consigli agronomici di
GreenThumb valgono solo se documentati qui.

Puoi riformulare la ricerca con termini diversi. Se la domanda e' pertinente al giardinaggio
o al negozio ma la knowledge base non la copre, dichiara al cliente che non hai
l'informazione e valuta l'escalation a un operatore (motivo: no_knowledge). Se invece la
domanda e' fuori ambito, rifiuta cortesemente senza aprire un'escalation."""


class KnowledgeBaseInput(BaseModel):
    """Input schema for the knowledge base search tool."""

    query: str = Field(
        description=(
            "La domanda riformulata come query di ricerca autonoma e specifica, non la "
            "frase letterale del cliente."
        )
    )
    doc_type: Literal["product", "guide", "policy"] | None = Field(
        default=None,
        description=(
            "Restringe la ricerca a un tipo di documento. Lascialo vuoto se non sei sicuro."
        ),
    )


def _format_hits(hits: list[SearchHit]) -> str:
    """Render the retrieved chunks as the text the model reads.

    Args:
        hits: The chunks that passed the relevance threshold.

    Returns:
        The formatted excerpts, each labelled with its document identifier.
    """
    blocks = [f"--- [{hit.doc_id}] {hit.title} ---\n{hit.text}" for hit in hits]
    header = (
        f"Trovati {len(hits)} estratti rilevanti. Cita i doc_id che usi davvero "
        f"per formulare la risposta.\n"
    )
    return header + "\n\n".join(blocks)


def _artifact(
    query: str,
    doc_type: str | None,
    hits: list[SearchHit],
    all_hits: list[SearchHit],
    threshold: float,
) -> dict[str, Any]:
    """Build the structured record for the deterministic response layer.

    SPEC section 7 describes the artifact as a list of ``{doc_id, score, chunk_id}``. It is
    wrapped in a record here because ``response.py`` also needs the threshold that was
    applied and the best score seen, including when nothing passed: "retrieval ran and
    found nothing relevant" must be distinguishable from "retrieval never ran" when capping
    the confidence (SPEC section 5).

    Args:
        query: The executed query.
        doc_type: The document type filter, when one was applied.
        hits: The chunks above the threshold.
        all_hits: Every chunk returned, including those below the threshold.
        threshold: The relevance threshold applied.

    Returns:
        A JSON-serialisable record.
    """
    return {
        "tool": TOOL_NAME,
        "query": query,
        "doc_type": doc_type,
        "threshold": threshold,
        "best_similarity": max((h.similarity for h in all_hits), default=None),
        "results": [
            {"doc_id": hit.doc_id, "score": hit.similarity, "chunk_id": hit.chunk_id}
            for hit in hits
        ],
    }


def make_knowledge_base_tool(store: Chroma, top_k: int, score_low: float) -> StructuredTool:
    """Build the knowledge base search tool with its dependencies bound.

    Args:
        store: The Chroma vector store to query.
        top_k: How many chunks to retrieve before filtering.
        score_low: Minimum similarity for a chunk to count as relevant (ADR-040).

    Returns:
        The tool, ready to hand to ``create_agent``.
    """

    def _run(
        query: str, doc_type: Literal["product", "guide", "policy"] | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Search the knowledge base and format the result.

        Args:
            query: The reformulated search query.
            doc_type: Optional document type filter.

        Returns:
            The text for the model and the artifact for the response layer.
        """
        if not query or not query.strip():
            return EMPTY_QUERY_MESSAGE, _artifact("", doc_type, [], [], score_low)

        all_hits = search(store, query.strip(), top_k=top_k, doc_type=doc_type)
        relevant = [hit for hit in all_hits if hit.similarity >= score_low]

        if not relevant:
            scope = f" (limitata ai documenti di tipo '{doc_type}')" if doc_type else ""
            message = NO_RESULTS_MESSAGE.format(query=query.strip(), scope=scope)
            return message, _artifact(query.strip(), doc_type, [], all_hits, score_low)

        return (
            _format_hits(relevant),
            _artifact(query.strip(), doc_type, relevant, all_hits, score_low),
        )

    return StructuredTool.from_function(
        func=_run,
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        args_schema=KnowledgeBaseInput,
        response_format="content_and_artifact",
    )
