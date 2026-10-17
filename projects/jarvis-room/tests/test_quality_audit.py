"""Auditoria offline de formato e sinais textuais para revisão humana."""

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis_room.quality_audit import (
    audit_answer,
    audit_observations,
    count_complete_sentences,
    main,
)
from jarvis_room.quality_batch import evaluate_batch, load_observations
from jarvis_room.quality_evaluator import DEFAULT_PATH, evaluate_answer, load_cases


class TestQualityAudit(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = load_cases()
        self.case = self.cases["mqtt_basics"]
        self.observations = load_observations()

    def test_contagem_de_frases(self) -> None:
        for answer, expected in (
            ("MQTT é um protocolo. Usa broker.", 2),
            ("O que é MQTT? Explique!", 2),
            ("  Uma frase.\nOutra frase!  ", 2),
            ("Sem pontuação final", 0),
            ("", 0),
        ):
            with self.subTest(answer=answer):
                self.assertEqual(count_complete_sentences(answer), expected)

    def test_formato_independente_da_cobertura(self) -> None:
        for answer, expected in (
            ("MQTT é um protocolo. Usa broker.", True),
            ("Uma frase. Outra!  ", True),
            ("MQTT é um protocolo.", False),
            ("Uma. Duas. Três.", False),
            ("Uma. Duas. Trecho sem pontuação", False),
            ("", False),
        ):
            with self.subTest(answer=answer):
                result = audit_answer(self.case, answer)
                self.assertEqual(result.expected_sentences, 2)
                self.assertEqual(result.format_ok, expected)
                self.assertTrue(result.requires_human_review)
        answer = "MQTT é um protocolo publish/subscribe com broker."
        self.assertTrue(evaluate_answer(self.case, answer).passed)
        self.assertFalse(audit_answer(self.case, answer).format_ok)
        no_format_rule = audit_answer(self.cases["wled_basics"], "Sem pontuação")
        self.assertIsNone(no_format_rule.expected_sentences)
        self.assertTrue(no_format_rule.format_ok)
        self.assertEqual(no_format_rule.review_flags, ())
        self.assertTrue(no_format_rule.requires_human_review)

    def test_modelo_frio_sinalizado(self) -> None:
        result = audit_answer(self.case, self.observations[0]["answer"])
        self.assertEqual(result.sentence_count, 1)
        self.assertEqual(result.expected_sentences, 2)
        self.assertFalse(result.format_ok)
        self.assertEqual(result.review_flags, ("tecnologia de comunicacao sem fio",))
        self.assertTrue(result.requires_human_review)

    def test_precarregado_sinalizado(self) -> None:
        result = audit_answer(self.case, self.observations[1]["answer"])
        self.assertEqual(result.sentence_count, 1)
        self.assertFalse(result.format_ok)
        self.assertEqual(
            result.review_flags, ("sem necessidade de servidor intermediario",)
        )
        self.assertTrue(result.requires_human_review)

    def test_negacao_correta_exige_revisao(self) -> None:
        answer = (
            "MQTT não é uma tecnologia de comunicação sem fio. "
            "É um protocolo publish/subscribe que usa um broker."
        )
        result = audit_answer(self.case, answer)
        self.assertEqual(result.sentence_count, 2)
        self.assertTrue(result.format_ok)
        self.assertIn("tecnologia de comunicacao sem fio", result.review_flags)
        self.assertTrue(result.requires_human_review)
        self.assertTrue(evaluate_answer(self.case, answer).passed)

    def test_validacao_dos_novos_campos(self) -> None:
        original = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            for field, values in (
                ("expected_sentences", (0, -1, True, 2.0, "2", [], {})),
                ("review_phrases", (None, "texto", {}, [None], [42], [" "], ["?!"])),
            ):
                for value in values:
                    with self.subTest(field=field, value=value):
                        data = json.loads(json.dumps(original))
                        data["cases"][0][field] = value
                        path.write_text(json.dumps(data), encoding="utf-8")
                        with self.assertRaises(ValueError):
                            load_cases(path)
            # Os campos são opcionais; null não impõe quantidade de frases.
            for expected in (None, 1, 2):
                data = json.loads(json.dumps(original))
                data["cases"][0]["expected_sentences"] = expected
                data["cases"][0]["review_phrases"] = []
                path.write_text(json.dumps(data), encoding="utf-8")
                self.assertEqual(
                    load_cases(path)["mqtt_basics"]["expected_sentences"], expected
                )
            data["cases"][0].pop("expected_sentences")
            data["cases"][0].pop("review_phrases")
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertIn("mqtt_basics", load_cases(path))

    def test_auditoria_preserva_historico_e_avaliacao_lexical(self) -> None:
        original = json.loads(json.dumps(self.observations))
        report = audit_observations(self.observations)
        batch = evaluate_batch(self.observations)
        self.assertEqual(report["mode"], "offline")
        self.assertEqual(len(report["results"]), 2)
        self.assertEqual(self.observations, original)
        for lexical, audited in zip(batch["results"], report["results"]):
            for field, value in lexical.items():
                self.assertEqual(audited[field], value)
            self.assertEqual(audited["human_review"], "incorrect")
            self.assertTrue(audited["requires_human_review"])
        with self.assertRaisesRegex(ValueError, "Caso desconhecido"):
            audit_observations([{**self.observations[0], "case_id": "inexistente"}])

    def test_cli(self) -> None:
        expected = audit_observations(self.observations)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            observations = Path(directory) / "observations.json"
            observations.write_text(json.dumps({
                "schema_version": 1, "observations": self.observations,
            }), encoding="utf-8")
            with patch("sys.argv", [
                "quality_audit", "--observations", str(observations),
                "--output", str(output),
            ]), redirect_stdout(StringIO()) as stdout:
                main()
            self.assertIn(str(output), stdout.getvalue())
            self.assertEqual(json.loads(output.read_text()), expected)
            with patch("sys.argv", ["quality_audit"]), redirect_stdout(
                StringIO()
            ) as stdout:
                main()
            self.assertEqual(json.loads(stdout.getvalue()), expected)
            for flags in (
                ["--observations", str(Path(directory) / "missing.json")],
                ["--output", directory],
            ):
                with self.subTest(flags=flags), patch(
                    "sys.argv", ["quality_audit", *flags]
                ), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main()
                    self.assertEqual(error.exception.code, 2)
