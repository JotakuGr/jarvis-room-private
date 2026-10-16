"""Testes locais do inventário; não acessam Ollama ou Home Assistant."""

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from jarvis_room.capability_inventory import (
    DEFAULT_PATH,
    CapabilityStatus,
    load_inventory,
)


class TestCapabilityInventory(unittest.TestCase):
    def load_data(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_inventory(path)

    def load_modified(self, change):
        data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
        change(data)
        return self.load_data(data)

    def test_total_capabilities(self) -> None:
        self.assertEqual(len(load_inventory()), 10)

    def test_conversation_implemented(self) -> None:
        inventory = load_inventory()
        conversation = inventory["conversation"]
        self.assertEqual(conversation.id, "conversation")
        self.assertEqual(conversation.name, "Conversação restrita")
        self.assertEqual(conversation.status, CapabilityStatus.IMPLEMENTED)
        self.assertFalse(conversation.physical)
        self.assertIsNone(conversation.entity_id)

    def test_contagem_dos_estados(self) -> None:
        inventory = load_inventory()
        counts = Counter(capability.status for capability in inventory.values())
        self.assertEqual(counts[CapabilityStatus.IMPLEMENTED], 2)
        self.assertEqual(counts[CapabilityStatus.PLANNED], 8)
        self.assertEqual(counts[CapabilityStatus.CONNECTED], 0)
        self.assertEqual(counts[CapabilityStatus.VERIFIED], 0)
        self.assertTrue(all(item.entity_id is None for item in inventory.values()))

    def test_esquema_e_estrutura_invalidos(self) -> None:
        for data in (
            None,
            [],
            {},
            {"schema_version": 1},
            {"schema_version": 1, "capabilities": {}},
            {"schema_version": 1, "capabilities": None},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.load_data(data)
        for version in (0, 2, True, 1.0, "1", None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.load_modified(lambda data: data.update(schema_version=version))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('{"schema_version": 1,', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load_inventory(path)

    def test_campos_invalidos(self) -> None:
        for field in ("id", "name", "status", "physical", "entity_id"):
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.load_modified(lambda data: data["capabilities"][0].pop(field))
        for item in (None, "conversation", [], 1):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.load_modified(
                    lambda data: data["capabilities"].__setitem__(0, item)
                )
        for name in ("", "   ", 42, None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.load_modified(
                    lambda data: data["capabilities"][0].update(name=name)
                )
        for status in ("active", "", None, True, []):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.load_modified(
                    lambda data: data["capabilities"][0].update(status=status)
                )
        with self.assertRaises(ValueError):
            self.load_modified(
                lambda data: data["capabilities"][0].update(unexpected=True)
            )

    def test_identificadores_invalidos_ou_duplicados(self) -> None:
        for capability_id in ("", "Room", "room-light", "room lighting", None, 42):
            with self.subTest(id=capability_id), self.assertRaises(ValueError):
                self.load_modified(
                    lambda data: data["capabilities"][0].update(id=capability_id)
                )
        with self.assertRaisesRegex(ValueError, "duplicado"):
            self.load_modified(
                lambda data: data["capabilities"].append(data["capabilities"][0])
            )

    def test_physical_deve_ser_booleano(self) -> None:
        for physical in ("true", "false", 1, 0, None, []):
            with self.subTest(physical=physical), self.assertRaises(ValueError):
                self.load_modified(
                    lambda data: data["capabilities"][0].update(physical=physical)
                )

    def test_formato_entity_id(self) -> None:
        for entity_id in ("", "sala", "light.Sala", "light.sala\n", 42, False):
            with self.subTest(entity_id=entity_id), self.assertRaises(ValueError):
                self.load_modified(
                    lambda data: data["capabilities"][3].update(entity_id=entity_id)
                )
        inventory = self.load_modified(
            lambda data: data["capabilities"][3].update(entity_id="light.sala")
        )
        # Um identificador válido é só metadado; não eleva o status a conectado.
        self.assertEqual(inventory["room_lighting"].entity_id, "light.sala")
        self.assertEqual(inventory["room_lighting"].status, CapabilityStatus.PLANNED)

    def test_connected_exige_comprovacao_operacional(self) -> None:
        for index in (0, 3):
            with self.subTest(index=index), self.assertRaisesRegex(
                ValueError, "connected exige comprovação operacional"
            ):
                self.load_modified(
                    lambda data: data["capabilities"][index].update(
                        status="connected", entity_id="light.sala"
                    )
                )

    def test_verified_exige_comprovacao_operacional(self) -> None:
        for index in (0, 3):
            with self.subTest(index=index), self.assertRaisesRegex(
                ValueError, "verified exige comprovação operacional"
            ):
                self.load_modified(
                    lambda data: data["capabilities"][index].update(
                        status="verified", entity_id="light.sala"
                    )
                )
