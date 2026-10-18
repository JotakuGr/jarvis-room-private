"""Catálogo planejado: validações locais sem Home Assistant ou LLM."""

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis_room.home_assistant_catalog import (
    DEFAULT_PATH, DeviceCatalogError, assess_control, catalog_report, load_device_plans,
)
from jarvis_room.room_chat_cli import main


class TestHomeAssistantCatalog(unittest.TestCase):
    def changed(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            path.write_text(json.dumps(data))
            return load_device_plans(path)

    def test_seis_dispositivos_planejados(self):
        plans = load_device_plans()
        self.assertEqual(len(plans), 6)
        self.assertTrue(all(p.status == "planned" and p.home_assistant_entity_id is None for p in plans.values()))
        self.assertIsNone(plans["second_display_placeholder"].model)
        with self.assertRaises(FrozenInstanceError):
            plans["room_main_lights"].status = "connected"

    def test_hikvision_modelo_exato(self):
        board = load_device_plans()["hikvision_board"]
        self.assertEqual(board.manufacturer, "Hikvision")
        self.assertEqual(board.model, "DS-D5B65RB/D")

    def test_relatorio_offline(self):
        report = catalog_report()
        self.assertEqual(report["mode"], "offline")
        self.assertEqual(report["device_count"], 6)
        self.assertEqual(len(report["device_ids"]), 6)
        self.assertFalse(report["home_assistant_connected"])
        self.assertFalse(report["physical_control_enabled"])
        self.assertTrue(all("state" not in item for item in report["devices"]))

    def test_arquivo_ausente_e_json_invalido(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            for raw in (None, b"{", b"\xff", b"NaN", b"[]"):
                if raw is not None:
                    path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(DeviceCatalogError):
                    load_device_plans(path)
            self.assertEqual(assess_control("room_main_lights", "turn_on", path).reason, "catalog_unavailable")

    def test_campos_duplicados_e_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            for raw in ('{"schema_version":1,"schema_version":1,"devices":[]}',
                        DEFAULT_PATH.read_text().replace('"name":"Iluminação principal"', '"name":"a","name":"b"')):
                path.write_text(raw)
                with self.assertRaises(DeviceCatalogError):
                    load_device_plans(path)
        for version in (True, 1.0, "1", 2, None):
            with self.subTest(version=version), self.assertRaises(DeviceCatalogError):
                self.changed(lambda d: d.update(schema_version=version))
        for field, value in (("extra", 1), ("category", "switch"), ("category", []), ("name", " "),
                             ("manufacturer", 1), ("model", ""), ("model", False)):
            with self.subTest(field=field, value=value), self.assertRaises(DeviceCatalogError):
                self.changed(lambda d: d["devices"][0].update({field: value}))
        for change in (lambda d: d.update(devices=[]), lambda d: d.update(devices={}),
                       lambda d: d.update(extra=1), lambda d: d["devices"][0].pop("model")):
            with self.assertRaises(DeviceCatalogError):
                self.changed(change)

    def test_identificadores_e_duplicados(self):
        for identifier in (None, 1, "", "Room", "../room", "light.sala"):
            with self.subTest(identifier=identifier), self.assertRaises(DeviceCatalogError):
                self.changed(lambda d: d["devices"][0].update(id=identifier))
        with self.assertRaises(DeviceCatalogError):
            self.changed(lambda d: d["devices"].append(d["devices"][0]))

    def test_status_connected_ou_entity_id_rejeitados(self):
        for field, value in (("status", "connected"), ("status", "verified"), ("status", True),
                             ("home_assistant_entity_id", "light.sala"), ("home_assistant_entity_id", False)):
            with self.subTest(field=field, value=value), self.assertRaises(DeviceCatalogError):
                self.changed(lambda d: d["devices"][0].update({field: value}))

    def test_todas_acoes_bloqueadas_e_cli_preservada(self):
        for identifier in load_device_plans():
            for action in ("turn_on", "turn_off", "delete", None, []):
                self.assertFalse(assess_control(identifier, action).allowed)
        self.assertEqual(assess_control("unknown", "turn_on").reason, "unknown_device")
        self.assertEqual(assess_control("presence_sensor", "turn_on").reason, "read_only_device")
        self.assertEqual(assess_control("room_main_lights", "delete").reason, "unsupported_action")
        for message, expected in (("Quem é você?", "J.A.R.V.I.S."), ("Ligue a luz da sala", "Não executei")):
            with patch("sys.argv", ["room_chat_cli", message]), redirect_stdout(StringIO()) as out:
                main()
            self.assertIn(expected, out.getvalue())
            self.assertIn("acao_verificada=false", out.getvalue())
