"""Testes do benchmark offline."""

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis_room.quality_batch import evaluate_batch, load_observations, main


class TestQualityBatch(unittest.TestCase):
    def setUp(self) -> None:
        self.observations = load_observations()
        self.report = evaluate_batch(self.observations)

    def test_duas_observacoes(self) -> None:
        self.assertEqual(len(self.observations), 2)
        self.assertTrue(all(
            item["source"] == "user_report" for item in self.observations
        ))
        self.assertEqual(self.report["mode"], "offline")
        self.assertEqual(
            self.report["summary"], {"observations": 2, "models": 1, "cases": 1}
        )
        for original, result in zip(self.observations, self.report["results"]):
            for field, value in original.items():
                self.assertEqual(result[field], value)

    def test_modelo_frio_reprovado(self) -> None:
        cold = self.report["results"][0]
        self.assertEqual(cold["id"], "mqtt_17c_cold")
        self.assertFalse(cold["lexical_passed"])
        self.assertEqual(cold["lexical_coverage"], 0.0)
        self.assertEqual(cold["client_seconds"], 26.767375)
        self.assertEqual(len(cold["missing_concepts"]), 3)
        # "tecnologia de comunicação sem fio" não corresponde à expressão
        # literal "tecnologia sem fio" cadastrada no avaliador anterior.
        self.assertEqual(cold["forbidden_claims"], [])
        self.assertEqual(cold["human_review"], "incorrect")

    def test_precarregado_reprovado(self) -> None:
        preloaded = self.report["results"][1]
        self.assertEqual(preloaded["id"], "mqtt_17d_preloaded")
        self.assertFalse(preloaded["lexical_passed"])
        self.assertAlmostEqual(preloaded["lexical_coverage"], 1 / 3)
        self.assertEqual(preloaded["client_seconds"], 6.004)
        self.assertEqual(len(preloaded["missing_concepts"]), 2)
        self.assertEqual(
            preloaded["forbidden_claims"],
            ["sem necessidade de servidor intermediario"],
        )
        self.assertEqual(preloaded["human_review"], "incorrect")

    def test_revisao_humana_independente(self) -> None:
        for review in ("pending", "correct", "incorrect"):
            with self.subTest(review=review):
                entry = {**self.observations[0], "human_review": review}
                result = evaluate_batch([entry])["results"][0]
                self.assertEqual(result["human_review"], review)
                self.assertFalse(result["lexical_passed"])
                self.assertEqual(result["lexical_coverage"], 0.0)

    def test_caso_desconhecido(self) -> None:
        entry = {**self.observations[0], "case_id": "inexistente"}
        with self.assertRaisesRegex(ValueError, "Caso desconhecido"):
            evaluate_batch([entry])

    def test_observacoes_invalidas(self) -> None:
        invalid = [
            None,
            [],
            {},
            {"schema_version": True, "observations": self.observations},
            {"schema_version": 2, "observations": self.observations},
            {"schema_version": 1, "observations": None},
            {"schema_version": 1, "observations": []},
            {"schema_version": 1, "observations": [None]},
            {"schema_version": 1, "observations": [self.observations[0]] * 2},
        ]
        for field in ("id", "case_id", "model", "source", "answer"):
            for value in (None, " ", 42):
                entry = {**self.observations[0], field: value}
                invalid.append({"schema_version": 1, "observations": [entry]})
        for field, values in (
            ("load_state", (None, [], "hot")),
            ("human_review", (None, [], "approved")),
            ("client_seconds", (
                None, True, "6.0", -1, float("nan"), float("inf"),
                -float("inf"), 10 ** 400,
            )),
        ):
            for value in values:
                entry = {**self.observations[0], field: value}
                invalid.append({"schema_version": 1, "observations": [entry]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            for data in invalid:
                with self.subTest(data=data):
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_observations(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_observations(path)
        # Estado desconhecido e duração zero são registros válidos.
        entry = {
            **self.observations[0], "load_state": "unknown", "client_seconds": 0,
        }
        self.assertEqual(evaluate_batch([entry])["results"][0]["client_seconds"], 0)

    def test_cli_gera_relatorio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            observations = Path(directory) / "observations.json"
            observations.write_text(json.dumps({
                "schema_version": 1, "observations": self.observations,
            }), encoding="utf-8")
            with patch("sys.argv", [
                "quality_batch", "--observations", str(observations),
                "--output", str(output),
            ]), redirect_stdout(StringIO()) as stdout:
                main()
            self.assertEqual(json.loads(output.read_text()), self.report)
            self.assertIn(str(output), stdout.getvalue())
        with patch("sys.argv", ["quality_batch"]), redirect_stdout(StringIO()) as stdout:
            main()
        self.assertEqual(json.loads(stdout.getvalue()), self.report)

    def test_cli_erros_de_entrada_e_saida(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "ausente.json"
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            for flags in (
                ["--observations", str(missing)],
                ["--observations", str(invalid)],
                ["--output", directory],
            ):
                with self.subTest(flags=flags), patch(
                    "sys.argv", ["quality_batch", *flags]
                ), redirect_stderr(StringIO()) as stderr:
                    with self.assertRaises(SystemExit) as error:
                        main()
                    self.assertEqual(error.exception.code, 2)
                    self.assertIn("error:", stderr.getvalue())
