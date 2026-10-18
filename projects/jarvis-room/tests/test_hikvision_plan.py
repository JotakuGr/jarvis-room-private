"""Plano da lousa sem acesso serial, TCP ou equipamento real."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_room.hikvision_plan import (
    DEFAULT_PATH, HikvisionPlanError, assess_hikvision_command, hikvision_report, load_hikvision_plan,
)
from jarvis_room.home_assistant_catalog import DEFAULT_PATH as CATALOG_PATH


class TestHikvisionPlan(unittest.TestCase):
    def test_modelo(self):
        plan = load_hikvision_plan()
        self.assertEqual(plan.model, "DS-D5B65RB/D")
        self.assertEqual(plan.manufacturer, "Hikvision")

    def test_catalogo_vinculado(self):
        self.assertEqual(load_hikvision_plan().device_id, "hikvision_board")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            data = json.loads(CATALOG_PATH.read_text())
            data["devices"][3]["model"] = "outro-modelo"
            path.write_text(json.dumps(data))
            with self.assertRaises(HikvisionPlanError):
                load_hikvision_plan(catalog_path=path)

    def test_status_planejado(self):
        plan = load_hikvision_plan()
        self.assertEqual(plan.status, "planned")
        self.assertIsNone(plan.ha_entity_id)
        self.assertFalse(plan.control_protocol_verified)
        self.assertFalse(plan.network_control_verified)
        self.assertFalse(plan.rs232_command_set_verified)

    def test_interface_rs232_declarada(self):
        self.assertIn("RS-232", load_hikvision_plan().interfaces)
        for interface in ("RJ45", "HDMI IN", "HDMI OUT", "Touch-USB"):
            self.assertIn(interface, load_hikvision_plan().interfaces)

    def test_operacao_energia_negada(self):
        for command in ("power_on", "power_off"):
            result = assess_hikvision_command(command)
            self.assertFalse(result.allowed)
            self.assertEqual(result.reason, "protocol_not_verified")

    def test_selecao_entrada_negada(self):
        for command in ("set_input", "volume", "touch", "screen_cast", "delete", None, []):
            self.assertFalse(assess_hikvision_command(command).allowed)

    def test_dados_nao_autorizados_rejeitados(self):
        base = json.loads(DEFAULT_PATH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            self.assertFalse(assess_hikvision_command("power_on", path).allowed)
            invalid = [("model", "DS-D5B65RB"), ("status", "connected"), ("ha_entity_id", "media_player.board"),
                       ("control_protocol_verified", True), ("network_control_verified", True),
                       ("rs232_command_set_verified", True), ("rs232_command_set_verified", 0),
                       ("baudrate", 9600), ("ip", "invalid"), ("command", "power_on")]
            for field, value in invalid:
                path.write_text(json.dumps({**base, field: value}))
                with self.subTest(field=field), self.assertRaises(HikvisionPlanError):
                    load_hikvision_plan(path)
                self.assertFalse(assess_hikvision_command("power_on", path).allowed)
            for raw in ("{", DEFAULT_PATH.read_text().replace('"status": "planned"', '"status":"planned","status":"planned"')):
                path.write_text(raw)
                with self.assertRaises(HikvisionPlanError):
                    load_hikvision_plan(path)

    def test_nenhuma_chamada_fisica(self):
        with patch("socket.socket", side_effect=AssertionError("Sem rede")), patch("subprocess.Popen", side_effect=AssertionError("Sem processos externos")):
            self.assertFalse(hikvision_report()["physical_control_enabled"])
            self.assertFalse(assess_hikvision_command("power_on").allowed)
