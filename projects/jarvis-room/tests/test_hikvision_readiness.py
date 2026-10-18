"""Checklist sem elevar fatos desconhecidos a controle verificado."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_room.hikvision_readiness import DEFAULT_PATH, HikvisionReadinessError, load_hikvision_readiness, readiness_report


class TestHikvisionReadiness(unittest.TestCase):
    def test_modelo_correto(self):
        data = load_hikvision_readiness()
        self.assertEqual(data.model, "DS-D5B65RB/D")
        self.assertEqual(data.device_id, "hikvision_board")
        self.assertEqual(data.status, "planned")

    def test_hdmi_independente(self):
        data = load_hikvision_readiness()
        self.assertFalse(data.display_track.display_verified)
        self.assertEqual(data.display_track.host_computer, "unknown")
        self.assertEqual(data.display_track.hdmi_cable, "unknown")
        self.assertEqual(data.display_track.touch_usb_cable, "unknown")

    def test_protocolo_nao_verificado(self):
        data = load_hikvision_readiness()
        self.assertFalse(data.control_verified)
        self.assertFalse(data.control_track.rs232_protocol_verified)
        self.assertFalse(data.control_track.command_set_verified)
        self.assertFalse(data.control_track.state_feedback_verified)

    def test_firmware_ausente(self):
        self.assertEqual(load_hikvision_readiness().control_track.firmware, "unknown")

    def test_autorizacao_ausente(self):
        track = load_hikvision_readiness().control_track
        self.assertFalse(track.institutional_permission)
        self.assertFalse(track.network_access_authorized)
        self.assertEqual(track.equipment_available, "unknown")

    def test_adulteracao_json(self):
        base = json.loads(DEFAULT_PATH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            for field, value in (("control_verified", True), ("control_verified", 0), ("status", "connected"), ("model", "other"), ("ip", "invalid")):
                path.write_text(json.dumps({**base, field: value}))
                with self.assertRaises(HikvisionReadinessError):
                    load_hikvision_readiness(path)
            base["control_track"]["rs232_protocol_verified"] = True
            path.write_text(json.dumps(base))
            with self.assertRaises(HikvisionReadinessError):
                load_hikvision_readiness(path)
            path.write_text("{")
            with self.assertRaises(HikvisionReadinessError):
                load_hikvision_readiness(path)

    def test_relatorio_separa_exibicao_controle(self):
        report = readiness_report()
        self.assertFalse(report["display_is_equipment_control"])
        self.assertFalse(report["physical_control_enabled"])
        self.assertEqual(report["second_display_model"], "unknown")

    def test_nenhuma_chamada_fisica(self):
        with patch("socket.socket", side_effect=AssertionError("Sem rede")), patch("subprocess.Popen", side_effect=AssertionError("Sem subprocessos")):
            self.assertEqual(readiness_report()["mode"], "offline")
