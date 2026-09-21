"""Chunking, embedding and search over the knowledge base.

Design notes, with the reasoning recorded in DECISIONS.md:

* Chunking follows the Markdown headings first and only falls back to character splitting
  for oversized sections, because these documents are short and well structured: a fixed
  window would cut dosage tables and policy paragraphs in half.
* Every chunk is prefixed with the document title and its heading path. A chunk reading
  "Dose: 30 g/m²" is useless if it does not say which product it belongs to.
* multilingual-e5 is asymmetric and needs the ``query: `` / ``passage: `` prefixes, applied
  here so no caller can forget them (ADR-022).
* Chroma returns a cosine *distance*; similarity is ``1 - distance`` by our own explicit
  formula, so thresholds do not move when the library's normalisation changes (ADR-021).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from greenthumb.kb_loader import KbDocument, load_knowledge_base

HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
HEADER_KEYS = ("h1", "h2", "h3")

# Sections longer than this are split further; shorter ones stay whole.
MAX_SECTION_CHARS = 1200
SECTION_OVERLAP_CHARS = 150

COLLECTION_NAME = "greenthumb_kb"


class E5Embeddings(Embeddings):
    """multilingual-e5 wrapper that applies the mandatory asymmetric prefixes.

    The model was trained with ``query: `` on queries and ``passage: `` on documents.
    Omitting them degrades retrieval quietly rather than raising, so the prefixes live
    here instead of at the call sites.
    """

    def __init__(self, model_name: str) -> None:
        """Build the wrapper.

        Args:
            model_name: HuggingFace identifier of the embedding model.
        """
        self._inner = HuggingFaceEmbeddings(
            model_name=model_name,
            encode_kwargs={"normalize_embeddings": True},
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents with the ``passage: `` prefix.

        Args:
            texts: The document texts.

        Returns:
            One embedding vector per text.
        """
        return self._inner.embed_documents([f"passage: {text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        """Embed a query with the ``query: `` prefix.

        Args:
            text: The query text.

        Returns:
            The embedding vector.
        """
        return self._inner.embed_query(f"query: {text}")


@dataclass(frozen=True)
class SearchHit:
    """One retrieved chunk, with the numbers the deterministic layer needs.

    Attributes:
        doc_id: Identifier of the source document, extension included.
        title: Title of the source document.
        doc_type: One of ``product``, ``guide``, ``policy``.
        chunk_id: Stable identifier of the chunk within its document.
        text: The chunk text, title prefix included.
        similarity: Cosine similarity in ``[0, 1]``, computed as ``1 - distance``.
    """

    doc_id: str
    title: str
    doc_type: str
    chunk_id: str
    text: str
    similarity: float


def _heading_path(metadata: dict[str, str]) -> str:
    """Join the Markdown heading levels present on a chunk.

    Args:
        metadata: Chunk metadata produced by the header splitter.

    Returns:
        The heading path, for example ``"Resi e rimborsi > Spese e rimborso"``.
    """
    parts = [metadata[key] for key in HEADER_KEYS if metadata.get(key)]
    return " > ".join(parts)


def chunk_document(document: KbDocument) -> list[Document]:
    """Split one document into contextualised chunks.

    Args:
        document: The parsed knowledge base document.

    Returns:
        The chunks, each prefixed with the document title and heading path, and carrying
        the document's metadata plus ``chunk_id`` and ``heading_path``.
    """
    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS, strip_headers=False)
    sections = header_splitter.split_text(document.body)

    character_splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_SECTION_CHARS,
        chunk_overlap=SECTION_OVERLAP_CHARS,
        separators=["\n\n", "\n", ". ", " "],
    )

    chunks: list[Document] = []
    for section in sections:
        heading = _heading_path(section.metadata)
        pieces = (
            character_splitter.split_text(section.page_content)
            if len(section.page_content) > MAX_SECTION_CHARS
            else [section.page_content]
        )
        for piece in pieces:
            body = piece.strip()
            if not body:
                continue
            prefix = f"{document.title}"
            if heading:
                prefix = f"{prefix} — {heading}"
            index = len(chunks)
            metadata = dict(document.metadata)
            metadata["chunk_id"] = f"{document.doc_id}#{index}"
            metadata["heading_path"] = heading
            chunks.append(Document(page_content=f"{prefix}\n\n{body}", metadata=metadata))
    return chunks


def chunk_knowledge_base(documents: list[KbDocument]) -> list[Document]:
    """Chunk every document.

    Args:
        documents: The parsed knowledge base.

    Returns:
        All chunks, in document order.
    """
    chunks: list[Document] = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return chunks


def build_index(
    kb_root: pathlib.Path,
    persist_directory: pathlib.Path,
    embedding_model: str,
) -> tuple[Chroma, int]:
    """Build the vector store from scratch.

    Args:
        kb_root: Root of the knowledge base.
        persist_directory: Where Chroma persists the collection.
        embedding_model: HuggingFace identifier of the embedding model.

    Returns:
        A tuple of the populated store and the number of chunks indexed.
    """
    documents = load_knowledge_base(kb_root)
    chunks = chunk_knowledge_base(documents)

    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=E5Embeddings(embedding_model),
        persist_directory=str(persist_directory),
        collection_metadata={"hnsw:space": "cosine"},
    )
    # Deterministic ids make a rebuild idempotent instead of duplicating every chunk.
    store.add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])
    return store, len(chunks)


def open_index(persist_directory: pathlib.Path, embedding_model: str) -> Chroma:
    """Open an existing vector store.

    Args:
        persist_directory: Where Chroma persisted the collection.
        embedding_model: HuggingFace identifier of the embedding model.

    Returns:
        The store, ready to query.
    """
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=E5Embeddings(embedding_model),
        persist_directory=str(persist_directory),
        collection_metadata={"hnsw:space": "cosine"},
    )


def search(
    store: Chroma,
    query: str,
    top_k: int = 4,
    doc_type: str | None = None,
) -> list[SearchHit]:
    """Search the knowledge base.

    Args:
        store: The vector store to query.
        query: The (already reformulated) search query.
        top_k: How many chunks to return.
        doc_type: Optional filter on document type.

    Returns:
        The hits, ordered by decreasing similarity.

    Raises:
        ValueError: If the query is empty.
    """
    if not query.strip():
        raise ValueError("la query di ricerca non puo' essere vuota")

    where = {"doc_type": doc_type} if doc_type else None
    results = store.similarity_search_with_score(query, k=top_k, filter=where)

    return [
        SearchHit(
            doc_id=document.metadata["doc_id"],
            title=document.metadata["title"],
            doc_type=document.metadata["doc_type"],
            chunk_id=document.metadata["chunk_id"],
            text=document.page_content,
            similarity=round(1.0 - distance, 4),
        )
        for document, distance in results
    ]
