"""Tests for the knowledge base loader."""

from __future__ import annotations

import pathlib

import pytest

from greenthumb.config import get_settings
from greenthumb.kb_loader import KnowledgeBaseError, load_document, load_knowledge_base

VALID = """---
doc_id: guides/esempio.md
title: "Titolo: con due punti"
doc_type: guide
category: bulbi
season: [autunno, inverno]
related_skus: [GT-BUL-001, GT-BUL-002]
---

# Corpo

Testo del documento.
"""


def _write(root: pathlib.Path, relative: str, text: str) -> pathlib.Path:
    """Write a document into a temporary knowledge base.

    Args:
        root: Knowledge base root.
        relative: Path relative to the root.
        text: File contents.

    Returns:
        The absolute path written.
    """
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_frontmatter_and_body(tmp_path: pathlib.Path) -> None:
    """Metadata and body must be separated cleanly.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = _write(tmp_path, "guides/esempio.md", VALID)
    document = load_document(path, tmp_path)
    assert document.doc_id == "guides/esempio.md"
    assert document.title == "Titolo: con due punti"
    assert document.doc_type == "guide"
    assert document.body.startswith("# Corpo")
    assert "---" not in document.body


def test_list_fields_are_flattened_for_the_vector_store(tmp_path: pathlib.Path) -> None:
    """Chroma rejects list metadata, so lists are joined at load time (ADR-039).

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = _write(tmp_path, "guides/esempio.md", VALID)
    metadata = load_document(path, tmp_path).metadata
    assert metadata["season"] == "autunno,inverno"
    assert metadata["related_skus"] == "GT-BUL-001,GT-BUL-002"
    assert all(isinstance(value, str) for value in metadata.values())


def test_doc_id_disagreeing_with_the_path_is_rejected(tmp_path: pathlib.Path) -> None:
    """A drifting doc_id would break sources silently (ADR-006).

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = _write(
        tmp_path, "guides/esempio.md", VALID.replace("guides/esempio.md", "guides/altro.md")
    )
    with pytest.raises(KnowledgeBaseError, match="non coincide"):
        load_document(path, tmp_path)


def test_missing_required_field_is_rejected(tmp_path: pathlib.Path) -> None:
    """An untitled document would produce chunks with no context prefix.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = _write(
        tmp_path, "guides/esempio.md", VALID.replace('title: "Titolo: con due punti"', "")
    )
    with pytest.raises(KnowledgeBaseError, match="mancanti"):
        load_document(path, tmp_path)


def test_empty_knowledge_base_is_rejected(tmp_path: pathlib.Path) -> None:
    """Silently indexing nothing is worse than failing.

    Args:
        tmp_path: Pytest temporary directory.
    """
    (tmp_path / "kb").mkdir()
    with pytest.raises(KnowledgeBaseError, match="nessun documento"):
        load_knowledge_base(tmp_path / "kb")


def test_real_knowledge_base_loads_completely() -> None:
    """The committed knowledge base must parse without exceptions."""
    documents = load_knowledge_base(get_settings().kb_dir)
    assert len(documents) == 37
    assert [d.doc_id for d in documents] == sorted(d.doc_id for d in documents)
    assert all(d.body.strip() for d in documents)
