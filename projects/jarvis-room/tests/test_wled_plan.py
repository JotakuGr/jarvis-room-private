"""Premissas e recusas sem controladores, rede ou dimensionamento inventado."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_room.wled_plan import DEFAULT_PATH, WledPlanError, assess_wled_command, load_wled_plan, wled_report


class TestWledPlan(unittest.TestCase):
    def changed(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zones.json"
            path.write_text(json.dumps(data))
            return load_wled_plan(path)

    def test_premissas_12v_ws2815(self):
        plan = load_wled_plan()
        self.assertEqual(plan.led_type, "WS2815")
        self.assertEqual(plan.voltage_nominal_v, 12)
        self.assertEqual(plan.controller_family, "ESP32")
        self.assertEqual(plan.firmware, "WLED")
        self.assertEqual(plan.status, "planned")

    def test_contagem_declarativa(self):
        report = wled_report()
        self.assertEqual(report["declared_led_count"], 6000)
        self.assertFalse(report["installation_confirmed"])
        self.assertEqual(report["mode"], "offline")

    def test_arquivo_invalido(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zones.json"
            for raw in (None, "{", "[]", "{}", DEFAULT_PATH.read_text().replace('"length_m": 100', '"length_m":100,"length_m":100')):
                if raw is not None:
                    path.write_text(raw)
                with self.assertRaises(WledPlanError):
                    load_wled_plan(path)
                self.assertFalse(assess_wled_command("on", path).allowed)

    def test_tipagem_estrita(self):
        for field, value in (("schema_version", True), ("schema_version", 1.0), ("length_m", 100.0),
                             ("voltage_nominal_v", "12"), ("leds_per_meter", True),
                             ("power_design_verified", 0), ("physical_control_enabled", 0)):
            with self.subTest(field=field), self.assertRaises(WledPlanError):
                self.changed(lambda d: d.update({field: value}))

    def test_entrada_arbitraria_rejeitada(self):
        for field, value in (("status", "connected"), ("physical_control_enabled", True),
                             ("power_design_verified", True), ("voltage_nominal_v", 5),
                             ("length_m", 99), ("ip", "invalid"), ("token", "dummy"), ("power_watts", 1000)):
            with self.subTest(field=field), self.assertRaises(WledPlanError):
                self.changed(lambda d: d.update({field: value}))

    def test_potencia_ainda_nao_dimensionada(self):
        report = wled_report()
        self.assertFalse(report["power_dimensioned"])
        for key in ("total_power_watts", "power_supply_count", "controller_count"):
            self.assertIsNone(report[key])

    def test_todos_comandos_bloqueados(self):
        for command in ("on", "off", "color", "brightness", "effect", "delete", None, []):
            self.assertFalse(assess_wled_command(command).allowed)
        self.assertFalse(wled_report()["physical_control_enabled"])

    def test_nenhum_acesso_fisico(self):
        with patch("socket.socket", side_effect=AssertionError("Sem rede")), patch("subprocess.Popen", side_effect=AssertionError("Sem processos externos")):
            self.assertFalse(wled_report()["home_assistant_connected"])
            self.assertFalse(assess_wled_command("on").allowed)
