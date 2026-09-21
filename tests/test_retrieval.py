"""Tests for chunking and the e5 prefix handling.

These tests never load the embedding model: chunking is pure and testable on its own, and
the prefix behaviour is verified against a stub rather than a 1.1 GB download.
"""

from __future__ import annotations

from typing import Any

from greenthumb.config import get_settings
from greenthumb.kb_loader import KbDocument, load_knowledge_base
from greenthumb.retrieval import (
    MAX_SECTION_CHARS,
    E5Embeddings,
    chunk_document,
    chunk_knowledge_base,
)

DOCUMENT = KbDocument(
    doc_id="guides/esempio.md",
    title="Guida di esempio",
    doc_type="guide",
    category="bulbi",
    body=(
        "# Titolo principale\n\n"
        "Introduzione al documento.\n\n"
        "## Dosaggi\n\n"
        "Dose: 30 g/m² per distribuzione.\n\n"
        "### Dettaglio\n\n"
        "Due distribuzioni all'anno.\n"
    ),
    metadata={
        "doc_id": "guides/esempio.md",
        "title": "Guida di esempio",
        "doc_type": "guide",
        "category": "bulbi",
        "season": "autunno",
    },
)


def test_chunks_carry_the_document_metadata() -> None:
    """Metadata must survive chunking, or filtering and sources break."""
    chunks = chunk_document(DOCUMENT)
    assert chunks
    for chunk in chunks:
        assert chunk.metadata["doc_id"] == "guides/esempio.md"
        assert chunk.metadata["doc_type"] == "guide"
        assert chunk.metadata["category"] == "bulbi"
        assert chunk.metadata["season"] == "autunno"


def test_every_chunk_is_prefixed_with_the_document_title() -> None:
    """A chunk reading "Dose: 30 g/m2" is useless without saying what it describes."""
    for chunk in chunk_document(DOCUMENT):
        assert chunk.page_content.startswith("Guida di esempio")


def test_heading_path_is_recorded_and_prefixed() -> None:
    """The heading path disambiguates sections that share wording across documents."""
    chunks = chunk_document(DOCUMENT)
    dosage = next(c for c in chunks if "30 g/m²" in c.page_content)
    assert "Dosaggi" in dosage.metadata["heading_path"]
    assert "Dosaggi" in dosage.page_content.split("\n\n")[0]


def test_chunk_ids_are_unique_and_stable() -> None:
    """Ids key the vector store, so a rebuild must overwrite rather than duplicate."""
    first = [c.metadata["chunk_id"] for c in chunk_document(DOCUMENT)]
    second = [c.metadata["chunk_id"] for c in chunk_document(DOCUMENT)]
    assert first == second
    assert len(set(first)) == len(first)
    assert all(cid.startswith("guides/esempio.md#") for cid in first)


def test_no_empty_chunks() -> None:
    """Blank chunks waste index space and pollute retrieval."""
    for chunk in chunk_document(DOCUMENT):
        body = chunk.page_content.split("\n\n", 1)[1]
        assert body.strip()


def test_short_sections_are_not_split_further() -> None:
    """Short, well-structured sections are natural semantic units (SPEC 6).

    The sample document has three headings, so it must yield exactly three chunks: one per
    section, none of them split by character count.
    """
    chunks = chunk_document(DOCUMENT)
    assert all(len(c.page_content) <= MAX_SECTION_CHARS + 400 for c in chunks)
    headings = [c.metadata["heading_path"] for c in chunks]
    assert headings == [
        "Titolo principale",
        "Titolo principale > Dosaggi",
        "Titolo principale > Dosaggi > Dettaglio",
    ]


def test_long_sections_are_split() -> None:
    """Sections over the limit fall back to character splitting."""
    long_body = "# Titolo\n\n" + ("Frase lunga di riempimento. " * 200)
    document = KbDocument(
        doc_id="guides/lungo.md",
        title="Documento lungo",
        doc_type="guide",
        category="generale",
        body=long_body,
        metadata={
            "doc_id": "guides/lungo.md",
            "title": "Documento lungo",
            "doc_type": "guide",
            "category": "generale",
        },
    )
    chunks = chunk_document(document)
    assert len(chunks) > 1


def test_real_knowledge_base_chunks_cleanly() -> None:
    """Every committed document must produce usable chunks."""
    documents = load_knowledge_base(get_settings().kb_dir)
    chunks = chunk_knowledge_base(documents)
    assert len(chunks) > len(documents)
    ids = [c.metadata["chunk_id"] for c in chunks]
    assert len(set(ids)) == len(ids)
    covered = {c.metadata["doc_id"] for c in chunks}
    assert covered == {d.doc_id for d in documents}


class _StubEmbeddings:
    """Records the texts it is handed, standing in for the real model."""

    def __init__(self) -> None:
        """Initialise the recorder."""
        self.documents: list[str] = []
        self.queries: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Record document texts.

        Args:
            texts: The texts handed to the model.

        Returns:
            One dummy vector per text.
        """
        self.documents.extend(texts)
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        """Record a query text.

        Args:
            text: The query handed to the model.

        Returns:
            A dummy vector.
        """
        self.queries.append(text)
        return [0.0]


def _wrapper_with_stub() -> tuple[E5Embeddings, _StubEmbeddings]:
    """Build an E5Embeddings whose backend is a stub.

    Returns:
        The wrapper and the stub it writes to.
    """
    wrapper = E5Embeddings.__new__(E5Embeddings)
    stub = _StubEmbeddings()
    wrapper._inner = stub  # noqa: SLF001 - the point of the test is the wrapper's behaviour
    return wrapper, stub


def test_documents_get_the_passage_prefix() -> None:
    """e5 is asymmetric; without the prefix retrieval degrades silently."""
    wrapper, stub = _wrapper_with_stub()
    wrapper.embed_documents(["primo", "secondo"])
    assert stub.documents == ["passage: primo", "passage: secondo"]


def test_queries_get_the_query_prefix() -> None:
    """The query side needs its own prefix, different from the document side."""
    wrapper, stub = _wrapper_with_stub()
    wrapper.embed_query("quando pianto i bulbi?")
    assert stub.queries == ["query: quando pianto i bulbi?"]


def test_prefixes_are_not_applied_twice(_unused: Any = None) -> None:
    """Each call prefixes exactly once, so repeated use cannot compound them.

    Args:
        _unused: Unused, present only to keep the signature documented.
    """
    wrapper, stub = _wrapper_with_stub()
    wrapper.embed_documents(["testo"])
    wrapper.embed_documents(["testo"])
    assert stub.documents == ["passage: testo", "passage: testo"]
