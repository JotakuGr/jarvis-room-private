"""Limites provisórios de memória para inferência local experimental.

Esta verificação não reserva memória nem garante proteção contra OOM.
"""

import re
from dataclasses import dataclass
from pathlib import Path

GIB = 1024 ** 3
MIN_RAM_BYTES = 2 * GIB
MIN_SWAP_BYTES = 2 * GIB


class LocalInferenceUnavailable(RuntimeError):
    """A política de recursos impediu a inferência local."""


@dataclass(frozen=True)
class MemorySnapshot:
    available_ram_bytes: int
    free_swap_bytes: int


@dataclass(frozen=True)
class InferenceDecision:
    allowed: bool
    reason: str


def parse_meminfo(contents: str) -> MemorySnapshot:
    """Extrai os campos obrigatórios de /proc/meminfo e converte kB em bytes."""
    values = {}
    for line in contents.splitlines():
        key, separator, value = line.partition(":")
        key = key.strip()
        if key not in ("MemAvailable", "SwapFree"):
            continue
        fields = value.split()
        if (
            not separator
            or key in values
            or len(fields) != 2
            or fields[1] != "kB"
            or re.fullmatch(r"[0-9]+", fields[0]) is None
        ):
            raise ValueError(f"Campo de memória inválido: {key}")
        values[key] = int(fields[0]) * 1024

    if not all(key in values for key in ("MemAvailable", "SwapFree")):
        raise ValueError("Campos de memória obrigatórios ausentes.")

    return MemorySnapshot(
        available_ram_bytes=values["MemAvailable"],
        free_swap_bytes=values["SwapFree"],
    )


def evaluate_resources(snapshot: MemorySnapshot) -> InferenceDecision:
    if snapshot.available_ram_bytes < MIN_RAM_BYTES:
        return InferenceDecision(
            allowed=False,
            reason="RAM disponível insuficiente para inferência local.",
        )
    if snapshot.free_swap_bytes < MIN_SWAP_BYTES:
        return InferenceDecision(
            allowed=False,
            reason="Swap livre insuficiente para inferência local.",
        )
    return InferenceDecision(
        allowed=True,
        reason="Recursos mínimos disponíveis para teste experimental.",
    )


def check_current_resources(
    path: Path = Path("/proc/meminfo"),
) -> InferenceDecision:
    try:
        contents = path.read_text(encoding="utf-8")
        snapshot = parse_meminfo(contents)
        return evaluate_resources(snapshot)
    except (OSError, ValueError):
        return InferenceDecision(
            allowed=False,
            reason="Não foi possível verificar os recursos do sistema.",
        )


def main() -> None:
    decision = check_current_resources()
    print("Inferência permitida:", decision.allowed)
    print("Motivo:", decision.reason)


if __name__ == "__main__":
    main()
