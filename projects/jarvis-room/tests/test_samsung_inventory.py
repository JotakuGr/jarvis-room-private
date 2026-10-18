"""S4.1: entidades informadas pelo operador, sem descoberta de rede."""

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from jarvis_room.samsung_contract import (
    ON_SCRIPT, OFF_SCRIPT, TV_ENTITY_ID, SamsungLabError, SamsungRequest,
)
from jarvis_room.samsung_inventory import DEFAULT_PATH, inventory_report, load_samsung_inventory


class TestSamsungInventory(unittest.TestCase):
    def modified(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps(data))
            return load_samsung_inventory(path)

    def test_modelo_e_entidade_exatos(self):
        inventory = load_samsung_inventory()
        self.assertEqual(inventory.model, "LH32BETBLGGXZD")
        self.assertEqual(inventory.entity_id, TV_ENTITY_ID)
        with self.assertRaises(FrozenInstanceError):
            inventory.model = "other"

    def test_scripts_sem_presumir_renomeacao(self):
        self.assertEqual(SamsungRequest("turn_on").script_entity_id, ON_SCRIPT)
        self.assertEqual(SamsungRequest("turn_off").script_entity_id, OFF_SCRIPT)
        with self.assertRaises(SamsungLabError):
            self.modified(lambda d: d["scripts"].update(turn_on="script.script_jarvis_ligar_samsung"))

    def test_ausente_json_invalido_e_duplicado(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for contents in (None, "{", '{"schema_version":1,"schema_version":1}', "[]", "NaN"):
                if contents is not None:
                    path.write_text(contents)
                with self.subTest(contents=contents), self.assertRaises(SamsungLabError):
                    load_samsung_inventory(path)

    def test_versao_tipos_e_extras(self):
        for key, value in (("schema_version", True), ("schema_version", 2), ("token", "fake"), ("model", [])):
            with self.subTest(key=key), self.assertRaises(SamsungLabError):
                self.modified(lambda d: d.update({key: value}))

    def test_destinos_arbitrarios_negados(self):
        for url in ("http://192.0.2.1:8123", "https://example.com", "http://localhost:18123", "http://127.0.0.1:18123/other"):
            with self.subTest(url=url), self.assertRaises(SamsungLabError):
                self.modified(lambda d: d.update(base_url=url))

    def test_flags_nao_elevaveis(self):
        for key in ("execution_enabled_by_default", "llm_control_enabled", "independent_physical_verification"):
            with self.subTest(key=key), self.assertRaises(SamsungLabError):
                self.modified(lambda d: d.update({key: True}))

    def test_apenas_duas_acoes(self):
        for action in ("toggle", "volume", "turn_on; reboot", "Ligue a TV", None, [], True):
            with self.subTest(action=action), self.assertRaises(SamsungLabError):
                SamsungRequest(action)

    def test_relatorio_offline_sem_equipamento_habilitado(self):
        report = inventory_report()
        self.assertEqual(report["mode"], "offline")
        self.assertFalse(report["execution_enabled"])
        self.assertFalse(report["physical_action_verified"])
        self.assertFalse(report["live_entities_checked"])
