"""Benchmark offline de respostas registradas, sem LLM."""

import argparse
import json
import math
from pathlib import Path

from .quality_evaluator import evaluate_answer, load_cases

DEFAULT_OBSERVATIONS = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "observations.json"
)
VALID_STATES = frozenset({"cold", "preloaded", "unknown"})
VALID_REVIEWS = frozenset({"correct", "incorrect", "pending"})


def _validate_observations(entries: object) -> list[dict]:
    if not isinstance(entries, list) or not entries:
        raise ValueError("Observações ausentes ou inválidas.")
    identifiers = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Cada observação deve ser um objeto JSON.")
        for field in ("id", "case_id", "model", "source", "answer"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Campo {field} ausente ou inválido.")
        if entry["id"] in identifiers:
            raise ValueError(f"Identificador duplicado: {entry['id']}.")
        identifiers.add(entry["id"])
        state = entry.get("load_state")
        if not isinstance(state, str) or state not in VALID_STATES:
            raise ValueError("Estado de carregamento inválido.")
        review = entry.get("human_review")
        if not isinstance(review, str) or review not in VALID_REVIEWS:
            raise ValueError("Avaliação humana inválida.")
        seconds = entry.get("client_seconds")
        if type(seconds) not in (int, float):
            raise ValueError("Tempo do cliente deve ser numérico, finito e não negativo.")
        try:
            valid_seconds = math.isfinite(seconds) and seconds >= 0
        except OverflowError:
            valid_seconds = False
        if not valid_seconds:
            raise ValueError("Tempo do cliente deve ser numérico, finito e não negativo.")
    return entries


def load_observations(
    path: Path = DEFAULT_OBSERVATIONS,
) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
    ):
        raise ValueError("Versão ou estrutura inválida.")
    return _validate_observations(data.get("observations"))


def evaluate_batch(observations: list[dict]) -> dict:
    """Reavalia textos registrados, preservando os dados e a revisão humana."""
    observations = _validate_observations(observations)
    cases = load_cases()
    results = []
    for entry in observations:
        if entry["case_id"] not in cases:
            raise ValueError(f"Caso desconhecido: {entry['case_id']}.")
        result = evaluate_answer(cases[entry["case_id"]], entry["answer"])
        results.append({
            **entry,
            "lexical_passed": result.passed,
            "lexical_coverage": result.coverage,
            "missing_concepts": list(result.missing_concepts),
            "forbidden_claims": list(result.forbidden_claims),
        })
    return {
        "schema_version": 1,
        "mode": "offline",
        "notes": [
            "Respostas e tempos preservados das fontes declaradas; "
            "este benchmark não executa inferência nem mede latência.",
            "Cobertura lexical não mede correção semântica nem inteligência. "
            "Afirmações problemáticas e revisão humana são campos separados.",
            "Ausência de expressões proibidas detectadas não comprova correção; "
            "variações de redação podem escapar à correspondência literal.",
            "As observações não estabelecem uma classificação de modelos.",
        ],
        "summary": {
            "observations": len(observations),
            "models": len({item["model"] for item in observations}),
            "cases": len({item["case_id"] for item in observations}),
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark offline sem inferência")
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate_batch(load_observations(args.observations))
        contents = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output is not None:
            args.output.write_text(contents + "\n", encoding="utf-8")
        else:
            print(contents)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.output is not None:
        print(f"Relatório offline salvo em: {args.output}")


if __name__ == "__main__":
    main()
