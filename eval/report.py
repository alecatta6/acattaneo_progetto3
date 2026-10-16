"""Assemble ``eval/results/summary.md`` from the saved scores.

The report is generated rather than written by hand, because every number in it has to
come from a file that a reader can open — a figure typed into a report is a figure nobody
can check. What is *not* generated is the analysis: picking the three worst cases is
arithmetic, explaining why they failed is not. The generated file therefore ends with a
section the author fills in, and says so.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
from collections.abc import Sequence

from eval import metrics_deepeval, metrics_deterministic, metrics_ragas
from eval.runner import RESULTS_DIR, TRACES_PATH
from eval.traces import TurnTrace, load_traces

logger = logging.getLogger(__name__)

SUMMARY_PATH = RESULTS_DIR / "summary.md"
# Prosa scritta a mano, inclusa cosi' com'e' alla fine del report generato. Sta in un file
# suo perche' il report si rigenera a ogni esecuzione: scriverla dentro il file generato
# significherebbe perderla al giro successivo, ed e' il posto peggiore per l'unica parte del
# report che non si puo' calcolare (ADR-069).
ANALYSIS_PATH = RESULTS_DIR / "analysis.md"
WORST_CASES = 3


def _load_json(path: pathlib.Path) -> dict | None:
    """Read a score file if it exists.

    Args:
        path: The file written by one of the metric modules.

    Returns:
        The parsed payload, or ``None`` when that metric has not been run.
    """
    if not path.exists():
        logger.warning("Manca %s: la sezione corrispondente verra' omessa.", path.name)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _percent(value: float | None) -> str:
    """Format a fraction as a percentage.

    Args:
        value: The fraction, or ``None``.

    Returns:
        A percentage, or ``n/d``.
    """
    return "n/d" if value is None else f"{value:.1%}"


def _decimal(value: float | None) -> str:
    """Format a judged score.

    Args:
        value: The score, or ``None``.

    Returns:
        Three decimals, or ``n/d``.
    """
    return "n/d" if value is None else f"{value:.3f}"


def _deterministic_section(payload: dict) -> list[str]:
    """Render the deterministic metrics, overall and per category.

    Args:
        payload: The parsed ``deterministic.json``.

    Returns:
        The markdown lines.
    """
    lines = ["## Metriche deterministiche", "", "| Metrica | Valore | Turni |", "|---|---|---|"]
    for score in payload["overall"]:
        lines.append(
            f"| {score['name']} | {_percent(score['value'])} | {score['passed']}/{score['total']} |"
        )
    lines.append("")

    names = [score["name"] for score in payload["overall"]]
    categories = sorted(payload["by_category"])
    lines += [
        "### Per categoria",
        "",
        "| Categoria | " + " | ".join(names) + " |",
        "|---" * (len(names) + 1) + "|",
    ]
    for category in categories:
        cells = []
        for score in payload["by_category"][category]:
            cells.append(f"{_percent(score['value'])} ({score['passed']}/{score['total']})")
        lines.append(f"| `{category}` | " + " | ".join(cells) + " |")
    lines.append("")

    failures = [
        (score["name"], score["failures"]) for score in payload["overall"] if score["failures"]
    ]
    if failures:
        lines += ["### Turni che non rispettano l'attesa", ""]
        for name, cases in failures:
            lines.append(f"- **{name}**: {', '.join(cases)}")
        lines.append("")
    return lines


def _judged_section(title: str, payload: dict, count_key: str) -> list[str]:
    """Render a judged metric block.

    Args:
        title: The section heading.
        payload: The parsed score file.
        count_key: ``turns`` for RAGAS, ``items`` for DeepEval.

    Returns:
        The markdown lines.
    """
    lines = [f"## {title}", "", "| Metrica | Media | Valutati | Mancanti |", "|---|---|---|---|"]
    for metric, row in payload["summary"].items():
        lines.append(
            f"| {metric} | {_decimal(row['mean'])} | {row[count_key]} | {row['missing']} |"
        )
    lines.append("")

    lines += ["### Per categoria", "", "| Metrica | Categoria | Media |", "|---|---|---|"]
    for metric, row in payload["summary"].items():
        for category, mean in row["by_category"].items():
            lines.append(f"| {metric} | `{category}` | {_decimal(mean)} |")
    lines.append("")
    return lines


def _turn_scores(payloads: Sequence[dict | None]) -> dict[tuple[str, int | None], list[float]]:
    """Collect every judged score, keyed by the item it belongs to.

    Args:
        payloads: The parsed RAGAS and DeepEval payloads, either of which may be missing.

    Returns:
        The scores of each item, so that the weakest ones can be ranked.
    """
    collected: dict[tuple[str, int | None], list[float]] = {}
    for payload in payloads:
        if payload is None:
            continue
        for row in payload.get("turns", []) + payload.get("items", []):
            if row["value"] is None:
                continue
            key = (row["conversation_id"], row["turn_index"])
            collected.setdefault(key, []).append(float(row["value"]))
    return collected


def _worst_cases_section(traces: Sequence[TurnTrace], payloads: Sequence[dict | None]) -> list[str]:
    """Rank the weakest turns and leave room for the analysis.

    A turn that fails a deterministic expectation ranks below any merely low-scoring one:
    a wrong ``needs_human`` or a missing source is a defect, while a low judged score may
    be the metric's calibration rather than the system's behaviour (ADR-033).

    Args:
        traces: Every trace.
        payloads: The parsed judged payloads.

    Returns:
        The markdown lines.
    """
    judged = _turn_scores(payloads)
    ranked: list[tuple[float, int, TurnTrace]] = []
    for trace in traces:
        deterministic_failures = sum(
            [
                trace.needs_human != trace.expected_needs_human,
                bool(trace.expected_tools)
                and not set(trace.expected_tools) <= set(trace.tools_invoked),
                bool(trace.expected_sources)
                and not set(trace.expected_sources) <= set(trace.sources),
                trace.fallback,
            ]
        )
        scores = judged.get((trace.conversation_id, trace.turn_index), [])
        mean = sum(scores) / len(scores) if scores else 1.0
        ranked.append((mean, deterministic_failures, trace))

    ranked.sort(key=lambda row: (-row[1], row[0]))
    lines = [f"## I {WORST_CASES} casi peggiori", ""]
    for mean, failures, trace in ranked[:WORST_CASES]:
        lines += [
            f"### {trace.conversation_id}#{trace.turn_index} — `{trace.category}`",
            "",
            f"- **Domanda**: {trace.user}",
            f"- **Risposta**: {trace.answer}",
            f"- **Attese non rispettate**: {failures}",
            f"- **Media dei punteggi giudicati**: {_decimal(mean)}",
            f"- `needs_human`: {trace.needs_human} (atteso {trace.expected_needs_human})",
            f"- tool: {trace.tools_invoked or '—'} (attesi {trace.expected_tools or '—'})",
            f"- fonti: {trace.sources or '—'} (attese {trace.expected_sources or '—'})",
            "",
        ]
    return lines


def _analysis_section() -> list[str]:
    """Include the hand-written analysis, or say plainly that it is missing.

    Returns:
        The markdown lines.
    """
    if not ANALYSIS_PATH.exists():
        return [
            "## Analisi",
            "",
            f"_Non ancora scritta: va in `{ANALYSIS_PATH.name}`, che questo report include "
            "alla fine._",
            "",
        ]
    return [ANALYSIS_PATH.read_text(encoding="utf-8").rstrip(), ""]


def build_report(traces_path: pathlib.Path | None = None) -> str:
    """Build the report from whatever score files exist.

    Args:
        traces_path: The trace file; defaults to ``eval/results/traces.jsonl``.

    Returns:
        The markdown report.
    """
    traces = load_traces(traces_path or TRACES_PATH)
    deterministic = _load_json(metrics_deterministic.SCORES_PATH)
    ragas = _load_json(metrics_ragas.SCORES_PATH)
    deepeval = _load_json(metrics_deepeval.SCORES_PATH)

    conversations = len({trace.conversation_id for trace in traces})
    lines = [
        "# Risultati dell'evaluation",
        "",
        f"Generato da `eval/report.py` il {dt.date.today().isoformat()}. "
        f"{conversations} conversazioni, {len(traces)} turni.",
        "",
        "Tutto cio' che precede la sezione *Analisi* e' generato: i numeri vengono da "
        "`traces.jsonl`, `deterministic.json`, `ragas.json` e `deepeval.json`, in questa "
        "stessa cartella, e nessuna cifra e' stata trascritta a mano. L'analisi, che non si "
        "puo' calcolare, e' scritta in `analysis.md` e inclusa qui alla fine.",
        "",
    ]
    if deterministic:
        lines += _deterministic_section(deterministic)
    if ragas:
        lines += _judged_section("Metriche RAGAS", ragas, count_key="turns")
    if deepeval:
        lines += _judged_section("Metriche DeepEval", deepeval, count_key="items")
    lines += _worst_cases_section(traces, [ragas, deepeval])
    lines += _analysis_section()
    return "\n".join(lines)


def main() -> None:
    """Write the report next to the scores."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(build_report(), encoding="utf-8")
    print(f"Scritto {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
