import json
from dataclasses import FrozenInstanceError, replace

from jarvis_room.room_intent import parse_room_intent
from jarvis_room.room_scenes import DEFAULT_PATH, RoomPlanError, build_room_plan, load_room_scenes
from room_test_support import OfflineRoomTest


class TestRoomScenes(OfflineRoomTest):
    def modified(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        return self.json_file(data)

    def plan(self, message="Ative o modo apresentação", **options):
        return build_room_plan(parse_room_intent(message), **options)

    def test_apresentacao_resolve_seis_alvos(self):
        plan = self.plan()
        self.assertEqual(len(plan.steps), 6)
        self.assertEqual(plan.steps[0].device_id, "led_perimeter")
        self.assertEqual(plan.steps[-1].device_id, "room_audio")
        self.assertTrue(all(step.action == "turn_on" for step in plan.steps))
        self.assertFalse(plan.physical_control_enabled)

    def test_dependencias_leds_monitores_audio(self):
        plan = self.plan()
        monitors = [step for step in plan.steps if step.device_id not in ("led_perimeter", "room_audio")]
        self.assertTrue(all(step.depends_on == ("led_perimeter",) for step in monitors))
        self.assertEqual(set(plan.steps[-1].depends_on), {step.device_id for step in monitors})

    def test_encerramento_seguro_audio_monitores_leds(self):
        plan = self.plan("Encerrar apresentação")
        self.assertEqual(plan.steps[0].device_id, "room_audio")
        self.assertEqual(plan.steps[-1].device_id, "led_perimeter")
        self.assertTrue(all(step.action == "turn_off" for step in plan.steps))
        self.assertFalse({"host", "computer", "session", "controller"} & {step.device_id for step in plan.steps})

    def test_individual_e_grupo_geram_planos_tipados(self):
        self.assertEqual(len(self.plan("Ligue o monitor Samsung").steps), 1)
        self.assertEqual(len(self.plan("Desligue todas as TVs").steps), 4)
        self.assertFalse(any(s.execution_available for s in self.plan().steps))

    def test_deduplica_individual_ja_incluido_no_grupo(self):
        path = self.modified(lambda d: d["scenes"][0]["steps"].append({
            "id": "samsung_again", "target_kind": "device", "target_id": "samsung_lab_tv",
            "action": "turn_on", "depends_on": [],
        }))
        plan = self.plan(scenes_path=path)
        self.assertEqual(sum(s.device_id == "samsung_lab_tv" for s in plan.steps), 1)

    def test_dependencia_desconhecida(self):
        path = self.modified(lambda d: d["scenes"][0]["steps"][0].update(depends_on=["missing"]))
        with self.assertRaises(RoomPlanError):
            self.plan(scenes_path=path)

    def test_ciclo_de_configuracao(self):
        path = self.modified(lambda d: d["scenes"][0]["steps"][0].update(depends_on=["audio_on"]))
        with self.assertRaises(RoomPlanError):
            self.plan(scenes_path=path)

    def test_ciclo_apos_expansao_e_deduplicacao(self):
        path = self.modified(lambda d: d["scenes"][0]["steps"].append({
            "id": "leds_again", "target_kind": "group", "target_id": "leds",
            "action": "turn_on", "depends_on": ["audio_on"],
        }))
        with self.assertRaisesRegex(RoomPlanError, "cyclic_dependencies"):
            self.plan(scenes_path=path)

    def test_alvos_e_acoes_arbitrarias_rejeitados(self):
        for values in ({"target_id": "computer"}, {"target_kind": "service"}, {"action": "reboot"}, {"action": "turn_off"}):
            path = self.modified(lambda d: d["scenes"][0]["steps"][0].update(values))
            with self.subTest(values=values), self.assertRaises(RoomPlanError):
                self.plan(scenes_path=path)

    def test_versao_campos_tipos_e_duplicados_rejeitados(self):
        for change in (lambda d: d.update(schema_version=True), lambda d: d.update(token="bad"),
                       lambda d: d["scenes"][0]["steps"][0].update(depends_on="leds_on"),
                       lambda d: d["scenes"][0]["steps"].append(d["scenes"][0]["steps"][0]),
                       lambda d: d["scenes"].append(d["scenes"][0])):
            with self.subTest(change=change), self.assertRaises(RoomPlanError):
                load_room_scenes(self.modified(change))
        path = self.json_file({})
        path.write_text('{"mode":"offline","mode":"live"}')
        with self.assertRaises(RoomPlanError):
            load_room_scenes(path)

    def test_arquivo_ausente_ou_json_invalido(self):
        path = self.json_file({})
        path.write_text("{")
        with self.assertRaises(RoomPlanError):
            load_room_scenes(path)
        path.unlink()
        with self.assertRaises(RoomPlanError):
            load_room_scenes(path)

    def test_intencao_fabricada_rejeitada(self):
        intent = parse_room_intent("Ligue os LEDs")
        with self.assertRaises(RoomPlanError):
            build_room_plan(replace(intent, target_id="monitores"))
        for value in ("Ligue os LEDs", True, {"action": "turn_on"}):
            with self.subTest(value=value), self.assertRaises(RoomPlanError):
                build_room_plan(value)

    def test_capacidade_pendente_explicita_e_sensor_sem_plano(self):
        plan = self.plan("Ligue o monitor Jarvis")
        self.assertEqual(plan.steps[0].integration_status, "planned")
        self.assertTrue(plan.steps[0].capability_supported)
        self.assertFalse(plan.steps[0].execution_available)
        with self.assertRaises(RoomPlanError):
            self.plan("Ligue o sensor de presença")

    def test_plano_e_passos_imutaveis(self):
        with self.assertRaises(FrozenInstanceError):
            self.plan().physical_control_enabled = True
        with self.assertRaises(FrozenInstanceError):
            self.plan().steps[0].action = "turn_off"
