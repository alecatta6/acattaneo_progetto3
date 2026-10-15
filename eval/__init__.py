"""Evaluation harness.

The evaluation is split in two so that scoring does not require re-running the agent:
:mod:`eval.runner` replays the dataset once and saves the traces, and the metric modules
read those traces (SPEC section 10.2). Re-scoring after a change to a metric, or after a
judge returned a suspicious number, therefore costs judge calls only.
"""
