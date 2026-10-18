"""Pendências WLED não são preenchidas por suposições."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_room.wled_readiness import DEFAULT_PATH, WledReadinessError, load_wled_readiness, readiness_report


class TestWledReadiness(unittest.TestCase):
    def changed(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            path.write_text(json.dumps(data))
            return load_wled_readiness(path)

    def test_premissas(self):
        premises = dict(load_wled_readiness().premises)
        self.assertEqual((premises["led_type"], premises["voltage_nominal_v"]), ("WS2815", 12))
        self.assertEqual((premises["length_m"], premises["leds_per_meter"]), (100, 60))
        self.assertEqual((premises["controller_family"], premises["firmware"]), ("ESP32", "WLED"))

    def test_contagem_declarativa(self):
        report = readiness_report()
        self.assertEqual(report["premises"]["declared_led_count"], 6000)
        self.assertFalse(report["controller_connected"])
        self.assertIsNone(report["zones_count"])

    def test_dados_pendentes(self):
        report = readiness_report()
        self.assertTrue(all(value is None for value in report["pending_measurements"].values()))
        for field in ("strip_batch", "voltage_drop", "ground_reference", "refresh_rate_hz", "fuses"):
            self.assertIn(field, report["pending_measurements"])
        self.assertIsNone(report["total_power_watts"])
        self.assertIsNone(report["power_supply_count"])

    def test_flags_nao_elevaveis(self):
        for flag in ("controller_connected", "power_design_verified", "physical_control_enabled"):
            for value in (True, 0, "false"):
                with self.assertRaises(WledReadinessError):
                    self.changed(lambda d: d.update({flag: value}))

    def test_json_invalido(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            for raw in (None, "{", "[]", "{}", DEFAULT_PATH.read_text().replace('"schema_version": 1', '"schema_version":1,"schema_version":1')):
                if raw is not None:
                    path.write_text(raw)
                with self.assertRaises(WledReadinessError):
                    load_wled_readiness(path)
        with self.assertRaises(WledReadinessError):
            self.changed(lambda d: d.update(schema_version=True))

    def test_potencia_fusiveis_nao_inventados(self):
        for field, value in (("total_power_watts", 1000), ("fuses", "inventado"), ("power_supply_count", 1), ("cable_sections_mm2", 2.5)):
            with self.assertRaises(WledReadinessError):
                self.changed(lambda d: d["measurements"].update({field: value}))
        for change in (lambda d: d.update(status="connected"), lambda d: d.update(ip="invalid"), lambda d: d["premises"].update(length_m=100.0)):
            with self.assertRaises(WledReadinessError):
                self.changed(change)

    def test_nenhuma_chamada_wled(self):
        with patch("socket.socket", side_effect=AssertionError("Sem rede")), patch("subprocess.Popen", side_effect=AssertionError("Sem subprocessos")):
            self.assertFalse(readiness_report()["physical_control_enabled"])

    def test_relatorio_offline(self):
        report = readiness_report()
        self.assertEqual(report["mode"], "offline")
        self.assertEqual(report["status"], "planned")
        self.assertFalse(report["power_design_verified"])
        self.assertNotIn("state", report)
