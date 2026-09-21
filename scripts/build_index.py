"""(Re)build the Chroma vector store from the knowledge base.

The store is not versioned: it is rebuilt from data/kb/ by `make index`, both locally and
on a clean Colab runtime.

Run with: uv run python scripts/build_index.py
"""

from __future__ import annotations

import shutil
import time

from greenthumb.config import get_settings
from greenthumb.retrieval import build_index


def main() -> int:
    """Rebuild the index and report what was written.

    Returns:
        0 on success.
    """
    settings = get_settings()
    target = settings.vector_store_dir

    if target.exists():
        print(f"rimuovo l'indice esistente in {target.name}/")
        shutil.rmtree(target)

    print(f"modello di embedding: {settings.embedding_model}")
    print("costruzione dell'indice in corso (il primo avvio scarica il modello)...")
    started = time.monotonic()
    store, chunk_count = build_index(settings.kb_dir, target, settings.embedding_model)
    elapsed = time.monotonic() - started

    collection = store._collection  # noqa: SLF001 - count() is not re-exported by the wrapper
    print(
        f"indicizzati {chunk_count} chunk in {elapsed:.1f}s "
        f"(collezione: {collection.count()} elementi)"
    )
    print(f"indice scritto in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
