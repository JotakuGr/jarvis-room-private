import json
from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock

from jarvis_room.control_guard import ToolReceipt
from jarvis_room.room_device_registry import DEFAULT_PATH
from jarvis_room.room_intent import parse_room_intent
from jarvis_room.room_orchestrator import (
    RoomOrchestrationError, SimulationBackendInfo, SimulationObservation, SimulationUnavailable,
    future_authorization_scope, orchestrate_room_intent, run_room_plan,
)
from jarvis_room.room_scenes import RoomPlanError, build_room_plan
from room_simulation_fakes import FakeRoomBackend
from room_test_support import OfflineRoomTest
from samsung_fakes import FakeClock


class TestRoomOrchestrator(OfflineRoomTest):
    def run_intent(self, message="Ligue os monitores", **options):
        return orchestrate_room_intent(parse_room_intent(message), **options)

    def test_preview_default_inclui_todos_sem_backend(self):
        result = self.run_intent()
        self.assertEqual((result.mode, result.status, len(result.results)), ("offline_preview", "plan_ready", 4))
        self.assertEqual(result.results[0].outcome, "lab_integration_available")
        self.assertTrue(all(item.outcome == "pending_integration" for item in result.results[1:]))

    def test_individual_liga_e_desliga_simulados(self):
        for message, expected in (("Ligue o monitor Samsung", "on"), ("Desligue o monitor Samsung", "off")):
            with self.subTest(message=message):
                backend = FakeRoomBackend()
                result = self.run_intent(message, backend=backend)
                self.assertEqual(result.results[0].simulated_state, expected)
                self.assertEqual(result.status, "simulated_complete")
                self.assertEqual(len(backend.calls), 1)

    def test_grupo_liga_e_desliga_um_envio_por_dispositivo(self):
        for message, action in (("Ligue todas as TVs", "turn_on"), ("Desligue os monitores", "turn_off")):
            with self.subTest(message=message):
                backend = FakeRoomBackend()
                result = self.run_intent(message, backend=backend)
                self.assertEqual(len(backend.calls), 4)
                self.assertEqual(len(set(backend.calls)), 4)
                self.assertTrue(all(item[1] == action for item in backend.calls))
                self.assertTrue(all(not item.physical_action_verified and not item.action_verified for item in result.results))

    def test_cena_ordena_acoes_com_relogio_virtual(self):
        clock = FakeClock()
        backend = FakeRoomBackend(clock=clock)
        result = self.run_intent("Ative o modo apresentação", backend=backend, clock=clock.monotonic)
        self.assertEqual(result.elapsed_seconds, 1.5)
        self.assertEqual(backend.calls[0], ("led_perimeter", "turn_on"))
        self.assertEqual(backend.calls[-1], ("room_audio", "turn_on"))
        self.assertEqual(len(backend.calls), 6)

    def test_encerramento_sem_desligar_host(self):
        backend = FakeRoomBackend()
        result = self.run_intent("Encerrar apresentação", backend=backend)
        self.assertEqual(backend.calls[0], ("room_audio", "turn_off"))
        self.assertEqual(backend.calls[-1], ("led_perimeter", "turn_off"))
        self.assertEqual(result.status, "simulated_complete")

    def test_falha_parcial_nao_declara_cena_completa(self):
        backend = FakeRoomBackend({"samsung_lab_tv": RuntimeError("segredo")})
        result = self.run_intent("Ative o modo apresentação", backend=backend)
        self.assertEqual(result.status, "simulated_partial")
        outcomes = {item.device_id: item.outcome for item in result.results}
        self.assertEqual(outcomes["samsung_lab_tv"], "simulated_error")
        self.assertEqual(outcomes["room_audio"], "blocked_dependency")
        self.assertEqual(len(result.results), 6)
        self.assertEqual(len(backend.calls), 5)
        self.assertNotIn("segredo", json.dumps(result.report()))

    def test_falha_no_primeiro_passo_bloqueia_dependentes(self):
        backend = FakeRoomBackend({"led_perimeter": SimulationUnavailable("privado")})
        result = self.run_intent("Ative o modo apresentação", backend=backend)
        self.assertEqual(result.status, "simulated_failed")
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(len(result.results), 6)
        self.assertEqual(sum(item.outcome == "blocked_dependency" for item in result.results), 5)

    def test_estados_nao_confirmados_nao_sao_match(self):
        for state in ("off", "unknown", "unavailable"):
            with self.subTest(state=state):
                backend = FakeRoomBackend({"samsung_lab_tv": state})
                result = self.run_intent("Ligue o monitor Samsung", backend=backend)
                self.assertEqual(result.results[0].outcome, "simulated_unconfirmed")
                self.assertEqual(len(backend.calls), 1)

    def test_resultado_de_outro_dispositivo_ou_tool_receipt_recusado(self):
        for value in (SimulationObservation("room_audio", "turn_on", "on"),
                      ToolReceipt("home_assistant", "light.sala", "turn_on", True, True),
                      {"success": True, "physical_action_verified": True}):
            with self.subTest(value=type(value).__name__):
                result = self.run_intent("Ligue o monitor Samsung", backend=FakeRoomBackend({"samsung_lab_tv": value}))
                self.assertEqual(result.results[0].outcome, "simulated_error")
                self.assertFalse(result.physical_action_verified)

    def test_backend_fisico_ou_arbitrario_nao_e_aceito(self):
        for backend in (object(), Mock(info={"mode": "physical"}), "samsung_sprint5", True):
            with self.subTest(backend=type(backend).__name__), self.assertRaises(RoomOrchestrationError):
                self.run_intent(backend=backend)

    def test_metadado_adulterado_nao_habilita_backend(self):
        backend = FakeRoomBackend()
        object.__setattr__(backend.info, "physical_control_enabled", True)
        with self.assertRaises(RoomOrchestrationError):
            self.run_intent(backend=backend)
        self.assertEqual(backend.calls, [])

    def test_plano_adulterado_rejeitado_antes_do_backend(self):
        backend = FakeRoomBackend()
        plan = build_room_plan(parse_room_intent("Ligue os monitores"))
        invalid = replace(plan, steps=(replace(plan.steps[0], action="turn_off"), *plan.steps[1:]))
        with self.assertRaises(RoomOrchestrationError):
            run_room_plan(invalid, backend=backend)
        self.assertEqual(backend.calls, [])

    def test_sem_capacidade_nao_invoca_backend(self):
        data = json.loads(DEFAULT_PATH.read_text())
        data["devices"][1].update(capabilities=["read_state"], requires_physical_authorization=False)
        path = self.json_file(data)
        backend = FakeRoomBackend()
        result = self.run_intent(backend=backend, catalog_path=path)
        self.assertEqual(len(backend.calls), 3)
        self.assertEqual(result.results[1].outcome, "unsupported_capability")
        self.assertEqual(result.status, "simulated_partial")

    def test_escopo_futuro_enumera_alvos_sem_autorizar(self):
        scope = future_authorization_scope(build_room_plan(parse_room_intent("Ative o modo apresentação")))
        self.assertEqual(len(scope.targets), 6)
        self.assertFalse(scope.physical_execution_authorized)
        with self.assertRaises(FrozenInstanceError):
            scope.physical_execution_authorized = True

    def test_eventos_minimos_correlacionados_sem_texto_ou_token(self):
        result = self.run_intent(backend=FakeRoomBackend())
        self.assertEqual(len(result.events), 4)
        self.assertEqual(len({event.correlation_id for event in result.events}), 1)
        self.assertTrue(all(not event.physical_action_verified for event in result.events))
        payload = json.dumps(result.report())
        self.assertNotIn("token", payload)
        self.assertNotIn("prompt", payload)
        self.assertNotIn("http", payload)

    def test_catalogo_invalido_e_intencao_arbitraria_sem_efeitos(self):
        backend = FakeRoomBackend()
        for intent in ("Ligue os monitores", parse_room_intent("Não ligue os monitores")):
            with self.subTest(intent=type(intent).__name__), self.assertRaises(RoomPlanError):
                orchestrate_room_intent(intent, backend=backend)
        self.assertEqual(backend.calls, [])
