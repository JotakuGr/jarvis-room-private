import copy
import json
from dataclasses import FrozenInstanceError

from jarvis_room.room_device_registry import DEFAULT_PATH
from jarvis_room.room_groups import RoomGroupError, group_inventory_report, resolve_group
from room_test_support import OfflineRoomTest


class TestRoomGroups(OfflineRoomTest):
    def test_monitores_incluem_todas_as_telas(self):
        ids = {d.id for d in resolve_group("monitores").members}
        self.assertEqual(ids, {"samsung_lab_tv", "hikvision_board", "jarvis_interface_display", "second_display_placeholder"})

    def test_ausencia_grupo_tvs_ou_televisores(self):
        for group in ("TVs", "tvs", "televisores", "http://x", None, []):
            with self.subTest(group=group), self.assertRaises(RoomGroupError):
                resolve_group(group)

    def test_cada_grupo_resolve_sem_duplicacao(self):
        for group in ("monitores", "leds", "audio"):
            with self.subTest(group=group):
                ids = [d.id for d in resolve_group(group).members]
                self.assertEqual(len(ids), len(set(ids)))

    def test_pendentes_nao_desaparecem(self):
        members = resolve_group("monitores").members
        self.assertEqual(sum(d.integration_status == "planned" for d in members), 3)
        self.assertFalse(any(d.execution_available for d in members))

    def test_led_e_audio_sao_grupos_distintos(self):
        self.assertEqual([d.id for d in resolve_group("leds").members], ["led_perimeter"])
        self.assertEqual([d.id for d in resolve_group("audio").members], ["room_audio"])

    def test_sensor_e_ar_nao_inseridos_em_grupos_ficticios(self):
        all_ids = {d.id for group in ("monitores", "leds", "audio") for d in resolve_group(group).members}
        self.assertFalse({"presence_sensor", "air_conditioner", "room_main_lights"} & all_ids)

    def test_monitor_futuro_incluido_automaticamente_como_planejado(self):
        data = json.loads(DEFAULT_PATH.read_text())
        device = copy.deepcopy(data["devices"][2])
        device.update(id="new_monitor", aliases=["o novo monitor"], name="Monitor a confirmar")
        data["devices"].append(device)
        result = resolve_group("monitores", self.json_file(data))
        self.assertEqual(len(result.members), 5)
        self.assertEqual(result.members[-1].integration_status, "planned")

    def test_catalogo_invalido_recusado(self):
        with self.assertRaisesRegex(RoomGroupError, "group_catalog_unavailable"):
            resolve_group("monitores", self.json_file({}))

    def test_relatorio_offline_com_resultado_por_item(self):
        report = group_inventory_report()
        self.assertEqual(set(report["groups"]), {"monitores", "leds", "audio"})
        self.assertEqual(len(report["groups"]["monitores"]), 4)
        self.assertFalse(report["physical_control_enabled"])
        self.assertTrue(all("integration_status" in d for d in report["groups"]["monitores"]))

    def test_resolucao_imutavel(self):
        with self.assertRaises(FrozenInstanceError):
            resolve_group("monitores").group_id = "televisores"
