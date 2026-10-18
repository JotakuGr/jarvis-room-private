"""Associações virtuais restritas; nenhuma entidade real é descoberta."""

import json
import tempfile
import unittest
from pathlib import Path

from jarvis_room.ha_lab_bindings import (
    DEFAULT_PATH, HALabBindingError, load_ha_lab_bindings,
    require_lab_binding, validate_observed_binding,
)
from jarvis_room.home_assistant_catalog import load_device_plans


class TestHALabBindings(unittest.TestCase):
    def changed(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            path.write_text(json.dumps(data))
            return load_ha_lab_bindings(path)

    def test_helper_valido(self):
        binding = require_lab_binding("room_main_lights")
        self.assertEqual(binding.entity_id, "input_boolean.jarvis_lab_light")
        self.assertFalse(binding.physical)
        self.assertTrue(binding.read_only)
        self.assertEqual(binding.kind, "virtual_helper")
        self.assertTrue(all(device.status == "planned" for device in load_device_plans().values()))

    def test_id_desconhecido(self):
        for identifier in ("hikvision_board", "light.sala", None, []):
            with self.assertRaises(HALabBindingError):
                require_lab_binding(identifier)
        with self.assertRaises(HALabBindingError):
            self.changed(lambda d: d["bindings"][0].update(device_id="led_perimeter"))

    def test_dominio_nao_permitido(self):
        for entity in ("light.sala", "switch.lab", "media_player.board", "http://invalid.example", "input_boolean.real", "input_boolean.jarvis_lab_light/../x"):
            with self.subTest(entity=entity), self.assertRaises(HALabBindingError):
                self.changed(lambda d: d["bindings"][0].update(entity_id=entity))

    def test_duplicado(self):
        with self.assertRaises(HALabBindingError):
            self.changed(lambda d: d["bindings"].append(d["bindings"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            path.write_text(DEFAULT_PATH.read_text().replace('"schema_version": 1', '"schema_version":1,"schema_version":1'))
            with self.assertRaises(HALabBindingError):
                load_ha_lab_bindings(path)

    def test_tipo_invalido(self):
        for field, value in (("entity_id", None), ("device_id", []), ("kind", True), ("physical", 0), ("read_only", 1)):
            with self.assertRaises(HALabBindingError):
                self.changed(lambda d: d["bindings"][0].update({field: value}))
        for version in (True, 1.0, "1", 2):
            with self.assertRaises(HALabBindingError):
                self.changed(lambda d: d.update(schema_version=version))

    def test_flags_inseguras(self):
        for field, value in (("physical", True), ("read_only", False), ("kind", "physical_device"), ("extra", "not-allowed")):
            with self.assertRaises(HALabBindingError):
                self.changed(lambda d: d["bindings"][0].update({field: value}))

    def test_arquivo_invalido(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            for raw in (None, "{", "[]", "{}"):
                if raw is not None:
                    path.write_text(raw)
                with self.assertRaises(HALabBindingError):
                    load_ha_lab_bindings(path)
        for change in (lambda d: d.update(bindings=[]), lambda d: d.update(extra=True)):
            with self.assertRaises(HALabBindingError):
                self.changed(change)

    def test_vinculo_nao_confere_entidade_observada(self):
        binding = require_lab_binding("room_main_lights")
        validate_observed_binding(binding, binding.entity_id)
        for observed in ("light.sala", "input_boolean.jarvis_lab_other", None):
            with self.assertRaises(HALabBindingError):
                validate_observed_binding(binding, observed)
