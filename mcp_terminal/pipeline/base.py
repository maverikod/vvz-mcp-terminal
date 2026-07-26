"""Shared types for the project verification pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


CheckRunner = Callable[[], int]


@dataclass(frozen=True)
class Check:
    """One named pipeline check."""

    name: str
    description: str
    runner: CheckRunner
