import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from jarvis_room.room_device_registry import (
    DEFAULT_PATH, RoomRegistryError, legacy_catalog_links, load_room_devices, room_registry_report,
)
from jarvis_room.samsung_contract import TV_ENTITY_ID, SamsungLabError
from room_test_support import OfflineRoomTest


class TestRoomDeviceRegistry(OfflineRoomTest):
    def modified(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        return self.json_file(data)

    def test_catalogo_e_grupos_sem_tvs_duplicadas(self):
        devices = load_room_devices()
        self.assertEqual(len(devices), 9)
        monitors = [d for d in devices.values() if d.group == "monitores"]
        self.assertEqual(len(monitors), 4)
        self.assertEqual([d.id for d in devices.values() if d.entity_id == TV_ENTITY_ID], ["samsung_lab_tv"])
        self.assertNotIn("televisores", {d.group for d in devices.values()})
        self.assertTrue(all(not d.execution_available and not d.physical_control_enabled for d in devices.values()))

    def test_aliases_da_samsung_mesmo_dispositivo(self):
        device = load_room_devices()["samsung_lab_tv"]
        self.assertTrue({"a tv samsung", "a televisao samsung", "o monitor samsung"} <= set(device.aliases))
        self.assertEqual(device.integration_status, "lab_existing")

    def test_slots_nao_afirmam_telas_fisicas_adicionais(self):
        devices = load_room_devices()
        for identifier in ("jarvis_interface_display", "second_display_placeholder"):
            self.assertEqual(devices[identifier].record_kind, "planned_role")
            self.assertIsNone(devices[identifier].entity_id)
            self.assertIsNone(devices[identifier].model)
        self.assertEqual(legacy_catalog_links()["second_display_placeholder"], "second_display_placeholder")

    def test_vinculos_legados_completos_sem_alterar_fontes(self):
        links = legacy_catalog_links()
        self.assertEqual(len(links), 6)
        self.assertEqual(links["hikvision_board"], "hikvision_board")
        path = self.modified(lambda d: d["devices"][1].update(legacy_ids=["inventado"]))
        with self.assertRaises(RoomRegistryError):
            load_room_devices(path)

    def test_leds_e_audio_planejados_sem_entidade(self):
        devices = load_room_devices()
        assumptions = dict(devices["led_perimeter"].assumptions)
        self.assertEqual(assumptions["length_m"] * assumptions["leds_per_meter"], 6000)
        self.assertEqual(assumptions["voltage_nominal_v"], 12)
        self.assertFalse(assumptions["power_design_verified"])
        self.assertIsNone(devices["room_audio"].model)
        self.assertIsNone(devices["room_audio"].entity_id)

    def test_sensor_sem_capacidade_de_acionamento(self):
        self.assertEqual(load_room_devices()["presence_sensor"].capabilities, ("read_state",))
        path = self.modified(lambda d: d["devices"][-1].update(capabilities=["turn_on"], requires_physical_authorization=True))
        with self.assertRaises(RoomRegistryError):
            load_room_devices(path)

    def test_arquivo_ausente_json_e_chaves_duplicadas(self):
        path = self.json_file({})
        for raw in ("{", '{"schema_version":1,"schema_version":1,"devices":[]}', "NaN"):
            path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(RoomRegistryError):
                load_room_devices(path)
        path.unlink()
        with self.assertRaises(RoomRegistryError):
            load_room_devices(path)

    def test_versao_e_campos_exatos(self):
        for change in (lambda d: d.update(schema_version=True), lambda d: d.update(token="not-secret"),
                       lambda d: d["devices"][0].update(url="http://example.invalid")):
            with self.subTest(change=change), self.assertRaises(RoomRegistryError):
                load_room_devices(self.modified(change))

    def test_ids_invalidos_ou_duplicados(self):
        for value in (True, "bad.id", "a" * 65, "samsung_lab_tv"):
            with self.subTest(value=value), self.assertRaises(RoomRegistryError):
                load_room_devices(self.modified(lambda d: d["devices"][1].update(id=value)))

    def test_aliases_ambiguos_e_reservados(self):
        for alias in ("A TÉLÉVISÃO SAMSUNG", "os monitores", "os alto-falantes", "a TV Samsung\n", "http://x"):
            with self.subTest(alias=alias), self.assertRaises(RoomRegistryError):
                load_room_devices(self.modified(lambda d: d["devices"][1].update(aliases=[alias])))

    def test_capacidades_e_tipos_invalidos(self):
        for values in ({"capabilities": ["reboot"]}, {"capabilities": ["turn_on", "turn_on"]},
                       {"capabilities": [True]}, {"requires_physical_authorization": 1},
                       {"group": "televisores"}, {"execution_available": True}, {"execution_available": 0}):
            with self.subTest(values=values), self.assertRaises(RoomRegistryError):
                load_room_devices(self.modified(lambda d: d["devices"][0].update(values)))

    def test_sem_entidade_ou_adaptador_inventado(self):
        for values in ({"entity_id": "light.sala"}, {"adapter": "wled_http"}, {"integration_status": "verified"}):
            with self.subTest(values=values), self.assertRaises(RoomRegistryError):
                load_room_devices(self.modified(lambda d: d["devices"][4].update(values)))

    def test_cadastro_futuro_de_monitor_ainda_planejado(self):
        def add(data):
            device = copy.deepcopy(data["devices"][2])
            device.update(id="future_display", name="Tela futura", aliases=["o monitor futuro"], legacy_ids=[])
            data["devices"].append(device)
        devices = load_room_devices(self.modified(add))
        self.assertEqual(devices["future_display"].group, "monitores")
        self.assertFalse(devices["future_display"].execution_available)

    def test_rejeita_elevacao_de_premissas_eletricas(self):
        with self.assertRaises(RoomRegistryError):
            load_room_devices(self.modified(lambda d: d["devices"][4]["assumptions"].update(power_design_verified=True)))

    def test_rejeita_samsung_divergente_ou_legado_ausente(self):
        for target in ("jarvis_room.room_device_registry.load_samsung_inventory", "jarvis_room.room_device_registry.load_device_plans"):
            with self.subTest(target=target), patch(target, side_effect=SamsungLabError("invalid_inventory")):
                with self.assertRaisesRegex(RoomRegistryError, "room_catalog_unavailable"):
                    load_room_devices()

    def test_relatorio_offline_e_objeto_imutavel(self):
        report = room_registry_report()
        self.assertEqual(report["mode"], "offline")
        self.assertFalse(report["live_state_queried"])
        self.assertFalse(report["physical_control_enabled"])
        with self.assertRaises(FrozenInstanceError):
            load_room_devices()["samsung_lab_tv"].execution_available = True
