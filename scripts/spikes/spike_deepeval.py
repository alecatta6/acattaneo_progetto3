"""Spike 6: verify the DeepEval 4.x API against the installed package.

Performs no LLM calls: introspection only. Also checks how telemetry is disabled
(ADR-018), since a delivery notebook must not ship evaluation data to a third party.
"""

from __future__ import annotations

import inspect
import os

# Set before importing deepeval: the flag is read at import time.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")


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


def _fields(label: str, model: object) -> None:
    """Print the declared fields of a pydantic/dataclass test case.

    Args:
        label: Human-readable name for the output.
        model: The class to inspect.
    """
    declared = getattr(model, "model_fields", None)
    if declared:
        print(f"  {label} fields: {', '.join(declared)}")
        return
    annotations = getattr(model, "__annotations__", {})
    print(f"  {label} annotations: {', '.join(annotations)}" if annotations else f"  {label}: ?")


def main() -> None:
    """Report what the installed DeepEval actually exposes."""
    import deepeval

    print(f"deepeval {deepeval.__version__}\n")

    print("== telemetry ==")
    telemetry_vars = [k for k in os.environ if "TELEMETRY" in k.upper()]
    print("  env vars set:", telemetry_vars or "none")
    try:
        from deepeval.telemetry import telemetry_opt_out

        print("  telemetry_opt_out() ->", telemetry_opt_out())
    except Exception as exc:  # noqa: BLE001
        print(f"  deepeval.telemetry.telemetry_opt_out: {type(exc).__name__}: {exc}")

    print("\n== test cases ==")
    from deepeval.test_case import ConversationalTestCase, LLMTestCase

    _fields("LLMTestCase", LLMTestCase)
    _show("LLMTestCase.__init__", LLMTestCase.__init__)
    _fields("ConversationalTestCase", ConversationalTestCase)
    _show("ConversationalTestCase.__init__", ConversationalTestCase.__init__)
    try:
        from deepeval.test_case import Turn

        _fields("Turn", Turn)
        _show("Turn.__init__", Turn.__init__)
    except ImportError as exc:
        print(f"  Turn: not importable ({exc})")

    print("\n== metrics required by SPEC 10.3 ==")
    import deepeval.metrics as metrics_module

    for name in (
        "AnswerRelevancyMetric",
        "GEval",
        "ConversationalGEval",
        "KnowledgeRetentionMetric",
    ):
        obj = getattr(metrics_module, name, None)
        if obj is None:
            print(f"  {name}: NOT exported by deepeval.metrics")
            continue
        _show(name, obj.__init__)
        for method in ("measure", "a_measure"):
            if hasattr(obj, method):
                _show(f"{name}.{method}", getattr(obj, method))

    print("\n== available metric names (filtered) ==")
    exported = sorted(n for n in dir(metrics_module) if n.endswith("Metric") or n == "GEval")
    print("  ", ", ".join(exported))


if __name__ == "__main__":
    main()
