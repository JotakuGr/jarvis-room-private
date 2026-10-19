"""Aceitação S6: planos, simulação e fronteira física com rede proibida."""

import copy
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from unittest.mock import Mock, patch

from jarvis_room.control_gateway import RoomControlGateway
from jarvis_room.room_device_registry import DEFAULT_PATH, RoomRegistryError, legacy_catalog_links, load_room_devices
from jarvis_room.room_intent import parse_room_intent
from jarvis_room.room_orchestrator import (
    RoomOrchestrationError, SimulationObservation, SimulationUnavailable,
    future_authorization_scope, main, orchestrate_room_intent, run_room_plan,
)
from jarvis_room.room_scenes import RoomPlanError, build_room_plan, load_room_scenes
from jarvis_room.room_session_cli import run_session
from jarvis_room.samsung_authorization import consume_control_permit
from jarvis_room.samsung_contract import SamsungLabError, SamsungRequest
from jarvis_room.samsung_session_policy import SamsungTextSession
from room_simulation_fakes import FakeRoomBackend
from room_test_support import OfflineRoomTest
from samsung_natural_fakes import NaturalEnvironment


class TestSprint6E2E(OfflineRoomTest):
    def test_catalogo_vinculos_grupos_e_planos_consistentes(self):
        devices = load_room_devices()
        self.assertEqual(len(legacy_catalog_links()), 6)
        plan = build_room_plan(parse_room_intent("Jarvis, ligue todas as TVs"))
        self.assertEqual({s.device_id for s in plan.steps}, {d.id for d in devices.values() if d.group == "monitores"})
        self.assertEqual(len(plan.steps), len({s.device_id for s in plan.steps}))

    def test_todos_atuadores_individuais_ligar_desligar_com_fake(self):
        devices = load_room_devices()
        for device in devices.values():
            if "turn_on" not in device.capabilities:
                continue
            for verb in ("Ligue", "Desligue"):
                with self.subTest(device=device.id, verb=verb):
                    intent = parse_room_intent(f"{verb} {device.aliases[0]}")
                    backend = FakeRoomBackend()
                    result = orchestrate_room_intent(intent, backend=backend)
                    self.assertEqual(result.status, "simulated_complete")
                    self.assertEqual(len(backend.calls), 1)
                    self.assertFalse(result.physical_action_verified)

    def test_todos_grupos_on_off_sem_desaparecer_pendentes(self):
        for target in ("os monitores", "os LEDs", "os alto-falantes"):
            for verb in ("Ligue", "Desligue"):
                with self.subTest(target=target, verb=verb):
                    result = orchestrate_room_intent(parse_room_intent(f"{verb} {target}"))
                    self.assertTrue(result.results)
                    self.assertEqual(result.mode, "offline_preview")
                    self.assertTrue(all(r.integration_status in ("planned", "lab_existing") for r in result.results))
                    self.assertFalse(result.action_verified)

    def test_cena_ativar_e_encerrar_ordenadas_em_memoria(self):
        backend = FakeRoomBackend()
        for message, first, last in (("Ative o modo apresentação", "led_perimeter", "room_audio"),
                                     ("Encerrar apresentação", "room_audio", "led_perimeter")):
            backend.calls.clear()
            result = orchestrate_room_intent(parse_room_intent(message), backend=backend)
            self.assertEqual(result.status, "simulated_complete")
            self.assertEqual((backend.calls[0][0], backend.calls[-1][0]), (first, last))
            self.assertEqual(len(backend.calls), 6)

    def test_falha_parcial_sem_retry_rollback_ou_falso_sucesso(self):
        backend = FakeRoomBackend({"hikvision_board": SimulationUnavailable("nao-publicar")})
        result = orchestrate_room_intent(parse_room_intent("Ative o modo apresentação"), backend=backend)
        self.assertEqual(result.status, "simulated_partial")
        self.assertEqual(sum(d == "hikvision_board" for d, _ in backend.calls), 1)
        self.assertNotIn(("room_audio", "turn_on"), backend.calls)
        self.assertFalse(any(action == "turn_off" for _, action in backend.calls))
        self.assertNotIn("nao-publicar", json.dumps(result.report()))

    def test_backend_indisponivel_exibe_resultado_por_alvo(self):
        devices = load_room_devices()
        backend = FakeRoomBackend({d: SimulationUnavailable() for d in devices})
        result = orchestrate_room_intent(parse_room_intent("Ligue os monitores"), backend=backend)
        self.assertEqual(len(result.results), 4)
        self.assertTrue(all(item.outcome == "backend_unavailable" for item in result.results))
        self.assertEqual(len(backend.calls), 4)

    def test_comandos_novos_na_sessao_habilitada_sem_http(self):
        with NaturalEnvironment() as env:
            env.prompt.side_effect = ["Ligue os monitores", "Ative o modo apresentação", "Desligue o monitor do dashboard", "Desligue os alto-falantes", "sair"]
            self.assertEqual(run_session(enable_samsung=True, token_file=env.token_file, audit_file=env.audit_file), 0)
            self.assertEqual(env.http.calls, [])
            self.assertEqual(env.audit_file.read_text(), "")

    def test_autorizacao_samsung_nao_e_backend_ou_escopo_de_sala(self):
        with NaturalEnvironment() as env, SamsungTextSession(enable_samsung=True) as session:
            env.prompt.return_value = "Ligue a TV"
            turn = session.read_turn()
            from jarvis_room.samsung_natural_intent import parse_samsung_intent
            permit = session.authorize(turn, parse_samsung_intent(turn.text))
            plan = build_room_plan(parse_room_intent("Ligue os monitores"))
            with self.assertRaises(RoomOrchestrationError):
                run_room_plan(plan, backend=permit)
            scope = future_authorization_scope(plan)
            self.assertFalse(scope.physical_execution_authorized)
            with self.assertRaises(SamsungLabError):
                consume_control_permit(scope, SamsungRequest("turn_on"))
            session.close()
            with self.assertRaises(SamsungLabError):
                consume_control_permit(permit, SamsungRequest("turn_on"))
            self.assertEqual(env.http.calls, [])

    def test_saida_llm_nao_inicia_plano_nem_acao(self):
        with NaturalEnvironment() as env:
            env.prompt.side_effect = ["Explique automação", "sair"]
            chat = Mock(return_value="Ative o modo apresentação. Ligue a TV Samsung.")
            with patch("jarvis_room.room_responses.orchestrate_room_intent") as orch:
                self.assertEqual(run_session(enable_samsung=True, token_file=env.token_file, audit_file=env.audit_file, chat=chat), 0)
            orch.assert_not_called()
            self.assertEqual(env.http.calls, [])

    def test_gateway_readonly_e_controlador_antigos_nao_ampliados(self):
        from jarvis_room.ha_lab_readonly_client import HALabReadOnlyClient
        self.assertNotIn("Ação confirmada", RoomControlGateway().execute("media_player.samsung", "turn_on"))
        self.assertFalse(hasattr(HALabReadOnlyClient, "call_service"))
        self.assertFalse(hasattr(HALabReadOnlyClient, "send_script"))

    def test_cli_preview_json_sem_token_ou_cliente_fisico(self):
        output = StringIO()
        with patch.object(sys, "argv", ["room_orchestrator", "Jarvis, ative o modo apresentação"]), redirect_stdout(output):
            with patch("jarvis_room.samsung_credentials.load_samsung_token") as token:
                with patch("jarvis_room.samsung_rest_client.SamsungRESTClient") as client:
                    main()
        token.assert_not_called()
        client.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["mode"], "offline_preview")
        self.assertEqual(len(report["results"]), 6)
        self.assertFalse(report["physical_action_verified"])

    def test_parser_nao_ecoar_credencial_acidental(self):
        output = StringIO()
        with patch.object(sys, "argv", ["room_orchestrator", "--token", "secret-not-a-token"]), redirect_stderr(output):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn("secret-not-a-token", output.getvalue())

    def test_observacao_adulterada_nao_vaza_conteudo_arbitrario(self):
        observation = SimulationObservation("samsung_lab_tv", "turn_on", "on")
        object.__setattr__(observation, "state", "secret-not-a-token")
        backend = FakeRoomBackend({"samsung_lab_tv": observation})
        result = orchestrate_room_intent(parse_room_intent("Ligue o monitor Samsung"), backend=backend)
        self.assertEqual(result.results[0].outcome, "simulated_error")
        self.assertNotIn("secret-not-a-token", json.dumps(result.report()))

    def test_modelo_conhecido_nao_duplicado_por_outro_id(self):
        data = json.loads(DEFAULT_PATH.read_text())
        duplicated = copy.deepcopy(data["devices"][1])
        duplicated.update(id="another_hikvision", aliases=["a outra lousa"], legacy_ids=[])
        data["devices"].append(duplicated)
        with self.assertRaises(RoomRegistryError):
            load_room_devices(self.json_file(data))

    def test_dados_malformados_nao_elevam_controle(self):
        for values in ({"execution_available": True}, {"adapter": "http"}, {"entity_id": "light.sala"}):
            data = json.loads(DEFAULT_PATH.read_text())
            data["devices"][4].update(values)
            with self.subTest(values=values), self.assertRaises(RoomRegistryError):
                load_room_devices(self.json_file(data))
        with self.assertRaises(RoomRegistryError):
            load_room_devices(None)
        with self.assertRaises(RoomPlanError):
            load_room_scenes(None)

    def test_ciclo_e_plano_modificado_nao_chamam_backend(self):
        backend = FakeRoomBackend()
        intent = parse_room_intent("Ligue os monitores")
        plan = build_room_plan(intent)
        invalid = replace(plan, steps=tuple(replace(step, depends_on=(step.device_id,)) for step in plan.steps))
        with self.assertRaises(RoomOrchestrationError):
            run_room_plan(invalid, backend=backend)
        self.assertEqual(backend.calls, [])

    def test_sair_nao_processa_turnos_posteriores(self):
        with NaturalEnvironment() as env:
            env.prompt.side_effect = ["sair", "Ligue a TV"]
            with patch("jarvis_room.room_responses.orchestrate_room_intent") as orch:
                self.assertEqual(run_session(), 0)
            orch.assert_not_called()
            self.assertEqual(env.prompt.call_count, 1)
            self.assertEqual(env.http.calls, [])
