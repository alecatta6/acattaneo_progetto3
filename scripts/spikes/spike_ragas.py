"""Spike 5: verify the RAGAS 0.4 metric API against the installed package.

Performs no LLM calls: introspection only.
"""

from __future__ import annotations

import inspect
import typing


def _show(label: str, obj: object) -> None:
    """Print an object's signature, tolerating objects that have none.

    Args:
        label: Human-readable name for the output.
        obj: The class or callable to introspect.
    """
    try:
        print(f"  {label}{inspect.signature(obj)}")  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        print(f"  {label}: no signature ({exc})")


def main() -> None:
    """Report what the installed RAGAS actually exposes."""
    import ragas

    print(f"ragas {ragas.__version__}\n")

    print("== ragas.metrics.collections (the non-deprecated path, ADR-020) ==")
    from ragas.metrics import collections

    names = [n for n in dir(collections) if not n.startswith("_")]
    print("  exported:", ", ".join(sorted(names)))

    print("\n== metrics required by SPEC 10.3 ==")
    for name in (
        "Faithfulness",
        "ContextPrecisionWithReference",
        "LLMContextPrecisionWithReference",
    ):
        obj = getattr(collections, name, None)
        if obj is None:
            print(f"  {name}: NOT in ragas.metrics.collections")
            continue
        _show(name, obj)
        init = getattr(obj, "__init__", None)
        if init is not None:
            _show(f"{name}.__init__", init)
        for method in ("ascore", "score", "single_turn_ascore"):
            if hasattr(obj, method):
                _show(f"{name}.{method}", getattr(obj, method))

    print("\n== evaluate() ==")
    _show("ragas.evaluate", ragas.evaluate)

    print("\n== judge wiring ==")
    from ragas import llms as ragas_llms

    print(
        "  ragas.llms exports:",
        ", ".join(sorted(n for n in dir(ragas_llms) if not n.startswith("_"))),
    )
    for name in ("llm_factory", "instructor_llm_factory"):
        obj = getattr(ragas_llms, name, None)
        if obj is not None:
            _show(f"ragas.llms.{name}", obj)

    print("\n== dataset container ==")
    for module_name, attr in (
        ("ragas.dataset_schema", "EvaluationDataset"),
        ("ragas.dataset_schema", "SingleTurnSample"),
    ):
        try:
            mod = __import__(module_name, fromlist=[attr])
            obj = getattr(mod, attr)
            fields = getattr(obj, "model_fields", None)
            if fields is not None:
                print(f"  {attr} fields: {', '.join(fields)}")
            else:
                _show(attr, obj)
        except Exception as exc:  # noqa: BLE001
            print(f"  {module_name}.{attr}: {type(exc).__name__}: {exc}")

    if typing.TYPE_CHECKING:  # pragma: no cover
        pass


if __name__ == "__main__":
    main()
