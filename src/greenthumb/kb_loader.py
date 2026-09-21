"""Read the knowledge base from disk.

Each Markdown file carries YAML frontmatter (SPEC section 4.3) that becomes chunk metadata.
Two details matter downstream:

* ``doc_id`` includes the file extension and is the single identifier used everywhere, from
  chunk metadata to the ``sources`` field of the response (ADR-006).
* Chroma only accepts scalar metadata values, so list-valued fields are flattened here
  rather than at indexing time (ADR-039).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import frontmatter

REQUIRED_FIELDS = ("doc_id", "title", "doc_type", "category")
# Frontmatter fields that are lists in YAML but must be scalars in the vector store.
LIST_FIELDS = ("season", "related_skus")


class KnowledgeBaseError(RuntimeError):
    """Raised when a knowledge base document is malformed."""


@dataclass(frozen=True)
class KbDocument:
    """One knowledge base document, parsed but not yet chunked.

    Attributes:
        doc_id: Path relative to the knowledge base root, extension included.
        title: Human-readable title from the frontmatter.
        doc_type: One of ``product``, ``guide``, ``policy``.
        category: Merchandise category, or ``generale``.
        body: The Markdown body, without the frontmatter block.
        metadata: Flattened metadata, safe to hand to the vector store.
    """

    doc_id: str
    title: str
    doc_type: str
    category: str
    body: str
    metadata: dict[str, str] = field(default_factory=dict)


def _flatten(value: object) -> str:
    """Render a frontmatter value as a vector-store-safe string.

    Args:
        value: The raw YAML value.

    Returns:
        A comma-joined string for lists, otherwise the value as a string.
    """
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def load_document(path: pathlib.Path, kb_root: pathlib.Path) -> KbDocument:
    """Parse one Markdown file into a :class:`KbDocument`.

    Args:
        path: Absolute path to the Markdown file.
        kb_root: Root of the knowledge base, used to derive ``doc_id``.

    Returns:
        The parsed document.

    Raises:
        KnowledgeBaseError: If a required field is missing, or ``doc_id`` disagrees with
            the file's own path.
    """
    post = frontmatter.load(path)
    relative = str(path.relative_to(kb_root))

    missing = [key for key in REQUIRED_FIELDS if not str(post.get(key) or "").strip()]
    if missing:
        raise KnowledgeBaseError(f"{relative}: campi frontmatter mancanti {missing}")

    doc_id = str(post["doc_id"])
    if doc_id != relative:
        raise KnowledgeBaseError(
            f"{relative}: doc_id={doc_id!r} non coincide con il percorso del file"
        )

    metadata: dict[str, str] = {
        "doc_id": doc_id,
        "title": str(post["title"]),
        "doc_type": str(post["doc_type"]),
        "category": str(post["category"]),
    }
    for key in LIST_FIELDS:
        if post.get(key):
            metadata[key] = _flatten(post[key])

    return KbDocument(
        doc_id=doc_id,
        title=metadata["title"],
        doc_type=metadata["doc_type"],
        category=metadata["category"],
        body=post.content,
        metadata=metadata,
    )


def load_knowledge_base(kb_root: pathlib.Path) -> list[KbDocument]:
    """Load every Markdown document under the knowledge base root.

    Args:
        kb_root: Root directory of the knowledge base.

    Returns:
        The documents, sorted by ``doc_id`` so indexing order is reproducible.

    Raises:
        KnowledgeBaseError: If the root does not exist or contains no documents.
    """
    if not kb_root.is_dir():
        raise KnowledgeBaseError(f"knowledge base non trovata in {kb_root}")

    documents = [load_document(path, kb_root) for path in sorted(kb_root.rglob("*.md"))]
    if not documents:
        raise KnowledgeBaseError(f"nessun documento Markdown in {kb_root}")
    return sorted(documents, key=lambda doc: doc.doc_id)
