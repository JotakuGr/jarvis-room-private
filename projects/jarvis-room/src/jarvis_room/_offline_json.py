"""Leitura estrita compartilhada pelos planos offline da Sprint 2."""

import json
from pathlib import Path


def load_object(path: Path, error_type: type[ValueError]) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Chave JSON duplicada.")
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError("Constante JSON inválida.")

    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique,
            parse_constant=invalid_constant,
        )
        if not isinstance(data, dict):
            raise ValueError("Objeto JSON obrigatório.")
        return data
    except (OSError, ValueError, RecursionError) as exc:
        raise error_type("Plano offline ausente ou inválido.") from exc


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def matches_exact_plan(data: object, expected: object) -> bool:
    """Confere campos aninhados e tipos exatos, incluindo bool versus int."""
    if type(data) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(data) == set(expected) and all(
            matches_exact_plan(data[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(data) == len(expected) and all(
            matches_exact_plan(a, b) for a, b in zip(data, expected)
        )
    return data == expected
