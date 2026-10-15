"""Reading ``eval/conversations.jsonl``.

The dataset is read in one place because two consumers need it: the runner, which replays
it, and the tests, which validate it against the real knowledge base and orders (ADR-063).
"""

from __future__ import annotations

import json
import pathlib

from pydantic import BaseModel, ConfigDict, Field

from greenthumb.config import REPO_ROOT

DATASET_PATH = REPO_ROOT / "eval" / "conversations.jsonl"


class DatasetTurn(BaseModel):
    """One turn of the dataset: the customer message and what is expected of it."""

    model_config = ConfigDict(frozen=True)

    user: str
    reference_answer: str
    expected_sources: list[str]
    expected_tools: list[str]
    expected_needs_human: bool


class Conversation(BaseModel):
    """One conversation of the dataset."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    category: str
    turns: list[DatasetTurn] = Field(min_length=1)


def load_conversations(path: pathlib.Path | None = None) -> list[Conversation]:
    """Load the evaluation dataset.

    Args:
        path: The dataset file; defaults to ``eval/conversations.jsonl``.

    Returns:
        The conversations, in file order.
    """
    path = path or DATASET_PATH
    return [
        Conversation.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
