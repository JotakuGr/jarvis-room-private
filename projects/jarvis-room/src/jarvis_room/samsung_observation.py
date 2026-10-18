"""Prazo e métricas de observação HA; não representam confirmação física."""

import math
from dataclasses import dataclass

from .samsung_contract import SamsungLabError

DEFAULT_OBSERVATION_SECONDS = 30.0
MAX_OBSERVATION_SECONDS = 30.0
OBSERVATION_OUTCOMES = frozenset({"not_started", "matched", "timed_out", "unavailable", "error"})


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True, slots=True)
class ObservationWindow:
    timeout_seconds: float = DEFAULT_OBSERVATION_SECONDS
    interval_seconds: float = 2.0

    def __post_init__(self):
        if (
            not _finite_number(self.timeout_seconds) or not 1 <= self.timeout_seconds <= MAX_OBSERVATION_SECONDS
            or not _finite_number(self.interval_seconds) or not 0.5 <= self.interval_seconds <= 5
        ):
            raise SamsungLabError("invalid_configuration")


@dataclass(frozen=True, slots=True)
class ObservationSummary:
    query_count: int = 0
    elapsed_seconds: float = 0.0
    timeout_seconds: float = 0.0
    outcome: str = "not_started"

    def __post_init__(self):
        if (
            type(self.query_count) is not int or self.query_count < 0
            or not _finite_number(self.elapsed_seconds) or self.elapsed_seconds < 0
            or not _finite_number(self.timeout_seconds) or not 0 <= self.timeout_seconds <= MAX_OBSERVATION_SECONDS
            or not isinstance(self.outcome, str) or self.outcome not in OBSERVATION_OUTCOMES
        ):
            raise SamsungLabError("invalid_response")
        if self.outcome == "not_started" and (self.query_count != 0 or self.elapsed_seconds != 0):
            raise SamsungLabError("invalid_response")
        if self.outcome != "not_started" and self.timeout_seconds < 1:
            raise SamsungLabError("invalid_response")
        if self.outcome == "matched" and (self.query_count < 1 or self.elapsed_seconds > self.timeout_seconds):
            raise SamsungLabError("invalid_response")

    @property
    def message(self):
        return {
            "not_started": "Observação de estado não iniciada.",
            "matched": "O Home Assistant informou o estado desejado dentro do prazo de observação.",
            "timed_out": "O estado não foi confirmado dentro do prazo de observação.",
            "unavailable": "O estado ficou indisponível e não foi confirmado dentro do prazo de observação.",
            "error": "A consulta de estado foi interrompida por um erro.",
        }[self.outcome]
