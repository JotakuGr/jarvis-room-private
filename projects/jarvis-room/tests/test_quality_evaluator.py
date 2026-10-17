"""Avaliações reproduzíveis de textos locais, sem modelos ou APIs."""

import json
import tempfile
import unittest
from pathlib import Path

from jarvis_room.quality_evaluator import (
    DEFAULT_PATH,
    contains_phrase,
    evaluate_answer,
    load_cases,
)


class TestQualityEvaluator(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = load_cases()
        self.mqtt = self.cases["mqtt_basics"]

    def test_quatro_casos(self) -> None:
        self.assertEqual(
            set(self.cases),
            {
                "mqtt_basics",
                "room_lighting_status",
                "wled_basics",
                "home_assistant_room",
            },
        )

    def test_normalizacao(self) -> None:
        self.assertTrue(
            contains_phrase("Modelo Publish/Subscribe", "publish subscribe")
        )
        self.assertTrue(
            contains_phrase("PUBLICAÇÃO/ASSINATURA!", "publicacao assinatura")
        )
        self.assertTrue(contains_phrase("Um BROKER.", "broker"))
        for text, phrase in (
            ("protocolos", "protocolo"),
            ("leds", "led"),
            ("", ""),
            ("texto", "?!"),
        ):
            with self.subTest(text=text, phrase=phrase):
                self.assertFalse(contains_phrase(text, phrase))

    def test_resposta_mqtt_correta(self) -> None:
        for answer in (
            "MQTT é um protocolo leve de mensagens publish/subscribe. "
            "Um broker distribui mensagens entre clientes.",
            "MQTT é um protocolo de publicação/assinatura. "
            "Um servidor intermediário distribui mensagens.",
        ):
            with self.subTest(answer=answer):
                result = evaluate_answer(self.mqtt, answer)
                self.assertEqual(result.case_id, "mqtt_basics")
                self.assertTrue(result.passed)
                self.assertEqual(result.coverage, 1.0)
                self.assertEqual(result.missing_concepts, ())
                self.assertEqual(result.forbidden_claims, ())

    def test_baseline_mqtt_incorreta(self) -> None:
        answer = (
            "A MQTT é uma tecnologia de comunicação de rede leve que permite "
            "a troca de mensagens sem necessidade de servidor intermediário, "
            "ideal para sistemas embarcados e IoT."
        )
        result = evaluate_answer(self.mqtt, answer)
        self.assertFalse(result.passed)
        self.assertAlmostEqual(result.coverage, 1 / 3)
        self.assertEqual(
            result.missing_concepts,
            ("protocolo", "publish subscribe | publicacao assinatura"),
        )
        self.assertEqual(
            result.forbidden_claims,
            ("sem necessidade de servidor intermediario",),
        )

    def test_conceitos_ausentes(self) -> None:
        for answer, coverage, missing_count in (("", 0, 3), ("Protocolo", 1 / 3, 2)):
            with self.subTest(answer=answer):
                result = evaluate_answer(self.mqtt, answer)
                self.assertFalse(result.passed)
                self.assertAlmostEqual(result.coverage, coverage)
                self.assertEqual(len(result.missing_concepts), missing_count)
                self.assertEqual(result.forbidden_claims, ())

    def test_afirmacoes_proibidas_reprovam_cobertura_completa(self) -> None:
        for claim in self.mqtt["forbidden"]:
            with self.subTest(claim=claim):
                result = evaluate_answer(
                    self.mqtt,
                    "MQTT é um protocolo publish/subscribe com broker. " + claim,
                )
                self.assertEqual(result.coverage, 1.0)
                self.assertFalse(result.passed)
                self.assertIn(claim, result.forbidden_claims)

    def test_demais_casos(self) -> None:
        answers = {
            "room_lighting_status": "Ainda não há integração para controle físico.",
            "wled_basics": "WLED é um firmware para LEDs em ESP32 e ESP8266.",
            "home_assistant_room": (
                "Home Assistant é uma plataforma de automação planejada para a sala."
            ),
        }
        for case_id, answer in answers.items():
            with self.subTest(case_id=case_id):
                case = self.cases[case_id]
                self.assertTrue(evaluate_answer(case, answer).passed)
                for claim in case["forbidden"]:
                    self.assertFalse(evaluate_answer(case, answer + " " + claim).passed)

    def test_catalogo_invalido(self) -> None:
        data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
        invalid_catalogs = [
            None,
            [],
            {},
            {"schema_version": True, "cases": data["cases"]},
            {"schema_version": 2, "cases": data["cases"]},
            {"schema_version": 1, "cases": []},
            {"schema_version": 1, "cases": {}},
            {"schema_version": 1, "cases": [None]},
            {"schema_version": 1, "cases": [self.mqtt, self.mqtt]},
        ]
        for field, values in (
            ("id", (None, "")),
            ("prompt", (None, " ", "?!")),
            ("required", (None, [], [None], [[]], [[42]], [[" "]], [["?!"]])),
            ("forbidden", (None, "broker", [42], [" "], ["?!"])),
        ):
            for value in values:
                case = dict(self.mqtt)
                case[field] = value
                invalid_catalogs.append({"schema_version": 1, "cases": [case]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            for catalog in invalid_catalogs:
                with self.subTest(catalog=catalog):
                    path.write_text(json.dumps(catalog), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_cases(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_cases(path)
