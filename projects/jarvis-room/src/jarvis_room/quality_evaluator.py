"""Avaliação lexical de respostas, sem inferência.

A cobertura mede grupos de expressões encontrados, não correção semântica.
Negações, coerência e formato ainda exigem revisão humana.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from .command_router import normalize

DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "quality_cases.json"
)


@dataclass(frozen=True)
class QualityResult:
    case_id: str
    passed: bool
    coverage: float
    missing_concepts: tuple[str, ...]
    forbidden_claims: tuple[str, ...]


def contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {normalize(text)} "
    normalized_phrase = normalize(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in normalized_text


def _valid_phrase(value: object) -> bool:
    return isinstance(value, str) and bool(normalize(value))


def load_cases(path: Path = DEFAULT_PATH) -> dict:
    """Valida o catálogo e indexa os casos por identificador único."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("O catálogo deve ser um objeto JSON.")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version deve ser o inteiro 1.")
    if not isinstance(data.get("cases"), list) or not data["cases"]:
        raise ValueError("cases deve ser uma lista não vazia.")

    cases = {}
    for case in data["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Cada caso deve ser um objeto JSON.")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Identificador de caso inválido.")
        if case_id in cases:
            raise ValueError(f"Identificador duplicado: {case_id}.")
        if not _valid_phrase(case.get("prompt")):
            raise ValueError(f"Prompt inválido no caso {case_id}.")
        required = case.get("required")
        if (
            not isinstance(required, list)
            or not required
            or any(
                not isinstance(group, list)
                or not group
                or not all(_valid_phrase(phrase) for phrase in group)
                for group in required
            )
        ):
            raise ValueError(f"Conceitos obrigatórios inválidos no caso {case_id}.")
        forbidden = case.get("forbidden")
        if not isinstance(forbidden, list) or not all(
            _valid_phrase(phrase) for phrase in forbidden
        ):
            raise ValueError(f"Afirmações proibidas inválidas no caso {case_id}.")
        expected_sentences = case.get("expected_sentences")
        if expected_sentences is not None and (
            type(expected_sentences) is not int or expected_sentences < 1
        ):
            raise ValueError(f"Quantidade de frases inválida no caso {case_id}.")
        review_phrases = case.get("review_phrases", [])
        if not isinstance(review_phrases, list) or not all(
            _valid_phrase(phrase) for phrase in review_phrases
        ):
            raise ValueError(f"Expressões de revisão inválidas no caso {case_id}.")
        cases[case_id] = case
    return cases


def evaluate_answer(case: dict, answer: str) -> QualityResult:
    """Exige uma alternativa por grupo e ausência de expressões proibidas."""
    missing = tuple(
        " | ".join(group)
        for group in case["required"]
        if not any(contains_phrase(answer, phrase) for phrase in group)
    )
    forbidden = tuple(
        phrase for phrase in case["forbidden"] if contains_phrase(answer, phrase)
    )
    return QualityResult(
        case_id=case["id"],
        passed=not missing and not forbidden,
        coverage=(len(case["required"]) - len(missing)) / len(case["required"]),
        missing_concepts=missing,
        forbidden_claims=forbidden,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação lexical sem inferência")
    parser.add_argument("--case", required=True, help="Identificador do caso")
    parser.add_argument("--answer-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        cases = load_cases()
        if args.case not in cases:
            parser.error(f"Caso desconhecido: {args.case}")
        answer = args.answer_file.read_text(encoding="utf-8")
        result = evaluate_answer(cases[args.case], answer)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Caso:", result.case_id)
    print("Aprovado:", result.passed)
    print(f"Cobertura: {result.coverage:.0%}")
    print("Conceitos ausentes:", result.missing_concepts)
    print("Afirmações problemáticas:", result.forbidden_claims)


if __name__ == "__main__":
    main()
