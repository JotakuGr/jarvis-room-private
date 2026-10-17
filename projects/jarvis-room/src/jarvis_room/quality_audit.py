"""Auditoria complementar de formato e revisão textual.

Não verifica verdade factual automaticamente.
Não executa modelos de linguagem.
"""

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .quality_batch import DEFAULT_OBSERVATIONS, load_observations
from .quality_evaluator import contains_phrase, evaluate_answer, load_cases


@dataclass(frozen=True)
class AuditResult:
    sentence_count: int
    expected_sentences: int | None
    format_ok: bool
    review_flags: tuple[str, ...]
    requires_human_review: bool = True


def count_complete_sentences(answer: str) -> int:
    """Estima frases por pontuação final; não é um segmentador completo."""
    return len(re.findall(r"[.!?](?=\s|$)", answer.strip()))


def audit_answer(case: dict, answer: str) -> AuditResult:
    expected = case.get("expected_sentences")
    count = count_complete_sentences(answer)
    if expected is None:
        format_ok = True
    else:
        format_ok = (
            count == expected
            and answer.rstrip().endswith((".", "!", "?"))
        )
    flags = tuple(
        phrase
        for phrase in case.get("review_phrases", [])
        if contains_phrase(answer, phrase)
    )
    return AuditResult(
        sentence_count=count,
        expected_sentences=expected,
        format_ok=format_ok,
        review_flags=flags,
        requires_human_review=True,
    )


def audit_observations(observations: list[dict]) -> dict:
    """Acrescenta a auditoria aos resultados, sem alterar a revisão registrada."""
    cases = load_cases()
    results = []
    for entry in observations:
        if entry["case_id"] not in cases:
            raise ValueError(f"Caso desconhecido: {entry['case_id']}.")
        case = cases[entry["case_id"]]
        lexical = evaluate_answer(case, entry["answer"])
        audit = audit_answer(case, entry["answer"])
        results.append({
            **entry,
            "lexical_passed": lexical.passed,
            "lexical_coverage": lexical.coverage,
            "missing_concepts": list(lexical.missing_concepts),
            "forbidden_claims": list(lexical.forbidden_claims),
            "sentence_count": audit.sentence_count,
            "expected_sentences": audit.expected_sentences,
            "format_ok": audit.format_ok,
            "review_flags": list(audit.review_flags),
            "requires_human_review": audit.requires_human_review,
        })
    return {
        "schema_version": 1,
        "mode": "offline",
        "notes": [
            "Textos, tempos e avaliações humanas preservados das fontes "
            "declaradas; esta auditoria não executa inferência.",
            "A contagem de frases é uma estimativa por pontuação final.",
            "Sinais textuais de revisão não provam erro factual e podem "
            "aparecer em frases corretas com negações.",
            "Cobertura lexical, formato e revisão humana são independentes; "
            "todos os resultados continuam sujeitos à revisão humana.",
        ],
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoria textual offline sem LLM")
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_observations(load_observations(args.observations))
        contents = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output is not None:
            args.output.write_text(contents + "\n", encoding="utf-8")
        else:
            print(contents)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.output is not None:
        print(f"Auditoria offline salva em: {args.output}")


if __name__ == "__main__":
    main()
