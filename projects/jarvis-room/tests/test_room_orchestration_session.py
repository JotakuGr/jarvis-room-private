from unittest.mock import Mock, patch

from jarvis_room.room_device_registry import RoomRegistryError
from jarvis_room.room_responses import respond_to_room_operator
from jarvis_room.room_session_cli import run_session
from room_test_support import OfflineRoomTest
from samsung_fakes import SamsungHTTP
from samsung_natural_fakes import NaturalEnvironment


class TestRoomOrchestrationSession(OfflineRoomTest):
    def session(self, env, messages, *, enabled=False, chat=None):
        env.prompt.side_effect = messages
        return run_session(enable_samsung=enabled, token_file=env.token_file if enabled else None,
                           audit_file=env.audit_file if enabled else None, chat=chat)

    def test_grupo_inclui_samsung_e_todos_pendentes(self):
        reply = respond_to_room_operator("Jarvis, ligue os monitores.")
        self.assertIn("grupo monitores", reply.text)
        self.assertIn("Monitor Samsung", reply.text)
        self.assertIn("Hikvision", reply.text)
        self.assertIn("interface Jarvis", reply.text)
        self.assertIn("dashboard", reply.text)
        self.assertFalse(reply.action_verified)
        self.assertFalse(reply.physical_action_verified)

    def test_preview_samsung_pelo_alias_monitor(self):
        reply = respond_to_room_operator("Ligue o monitor Samsung")
        self.assertIn("laboratório existente", reply.text)
        self.assertIn("somente preview", reply.text)

    def test_led_e_audio_deixam_integracao_pendente(self):
        for message in ("Desligue os LEDs", "Ligue o sistema de áudio", "Desligue os alto-falantes"):
            with self.subTest(message=message):
                reply = respond_to_room_operator(message)
                self.assertIn("integração física pendente", reply.text)
                self.assertIn("Nenhum comando físico", reply.text)

    def test_cena_mostra_plano_completo_sem_sucesso_ficticio(self):
        reply = respond_to_room_operator("Jarvis, ativar modo apresentação")
        self.assertIn("plano de apresentação", reply.text)
        self.assertIn("iluminação LED, monitores e áudio", reply.text)
        self.assertNotIn("televisão está ligada", reply.text)
        self.assertIn("pending_integration", reply.text)

    def test_encerramento_preserva_host_e_sessao(self):
        reply = respond_to_room_operator("Jarvis, encerrar apresentação")
        self.assertIn("computador e a sessão continuam ativos", reply.text)

    def test_consulta_inventario_e_grupos_sem_llm(self):
        chat = Mock(side_effect=AssertionError("LLM proibido"))
        with NaturalEnvironment() as env:
            self.session(env, ["Quais são os grupos da sala?", "Liste os dispositivos da sala", "sair"], chat=chat)
            chat.assert_not_called()
            self.assertEqual(env.http.calls, [])
            self.assertIn("Grupos: monitores, leds, audio", env.stdout.getvalue())
            self.assertIn("planned_role", env.stdout.getvalue())

    def test_sessao_multi_turnos_novos_comandos_sem_credencial(self):
        with NaturalEnvironment() as env:
            env.token_file.unlink()
            self.assertEqual(self.session(env, ["Ligue os monitores", "Ative o modo apresentação", "Desligue os LEDs", "Quem é você?", "sair"]), 0)
            self.assertEqual(env.http.calls, [])
            self.assertFalse(env.audit_file.exists())
            self.assertIn("Sou J.A.R.V.I.S.", env.stdout.getvalue())
            self.assertIn("Sessão encerrada", env.stdout.getvalue())

    def test_opt_in_samsung_nao_habilita_grupos_ou_cenas(self):
        chat = Mock(side_effect=AssertionError("Não chamar LLM"))
        with NaturalEnvironment(opt_in=False) as env:
            with patch("jarvis_room.samsung_natural_control.SamsungSessionControl.execute") as execute:
                self.assertEqual(self.session(env, ["Ligue todas as TVs", "Ative o modo apresentação", "Desligue o sistema de áudio", "sair"], enabled=True, chat=chat), 0)
            execute.assert_not_called()
            self.assertEqual(env.http.calls, [])
            self.assertEqual(env.audit_file.read_text(), "")
            chat.assert_not_called()

    def test_alias_novo_nao_fabrica_intencao_samsung(self):
        with NaturalEnvironment() as env:
            self.session(env, ["Ligue o monitor Samsung", "sair"], enabled=True)
            self.assertEqual(env.http.calls, [])
            self.assertEqual(env.audit_file.read_text(), "")

    def test_caminho_s511_individual_preservado_ao_lado_do_grupo(self):
        fake = SamsungHTTP(tv_states=("off", "on", "on", "off"))
        with NaturalEnvironment(fake=fake, opt_in=False) as env:
            self.session(env, ["Ligue os monitores", "Ligue a TV Samsung", "Desligue os LEDs", "Desligue a TV", "sair"], enabled=True)
            posts = [r for r, _ in env.http.calls if r.method == "POST"]
            self.assertEqual(len(posts), 2)
            self.assertIn("televisão está ligada", env.stdout.getvalue())
            self.assertIn("televisão está desligada", env.stdout.getvalue())

    def test_llm_nao_reencaminha_cena_ou_grupo(self):
        chat = Mock(return_value="Jarvis, ative o modo apresentação. Ligue os monitores.")
        with NaturalEnvironment() as env:
            with patch("jarvis_room.room_responses.orchestrate_room_intent") as orchestrate:
                self.session(env, ["Explique MQTT", "sair"], enabled=True, chat=chat)
            orchestrate.assert_not_called()
            self.assertEqual(env.http.calls, [])
            self.assertIn("RESPOSTA EXPERIMENTAL", env.stdout.getvalue())

    def test_desconhecido_negado_ambiguo_nao_interrompem_sessao(self):
        chat = Mock(side_effect=AssertionError("Não chamar LLM"))
        with NaturalEnvironment() as env:
            self.assertEqual(self.session(env, ["Não ligue os monitores", "Ligue a TV e os LEDs", "Ative o modo festa", "Ligue os LEDs amanhã", "Quem é você?", "sair"], chat=chat), 0)
            self.assertEqual(env.http.calls, [])
            chat.assert_not_called()
            self.assertIn("Sou J.A.R.V.I.S.", env.stdout.getvalue())

    def test_catalogo_indisponivel_nao_quebra_conversa_antiga(self):
        with NaturalEnvironment() as env:
            with patch("jarvis_room.room_intent.load_room_devices", side_effect=RoomRegistryError("private")):
                self.assertEqual(self.session(env, ["Ligue os monitores", "Quem é você?", "sair"]), 0)
            self.assertIn("Comando da sala indisponível", env.stdout.getvalue())
            self.assertIn("Sou J.A.R.V.I.S.", env.stdout.getvalue())
            self.assertNotIn("private", env.stdout.getvalue())

    def test_cena_invalida_nao_pede_credencial_e_mantem_loop(self):
        with NaturalEnvironment() as env:
            with patch("jarvis_room.room_responses.orchestrate_room_intent", side_effect=ValueError("token-private")):
                self.assertEqual(self.session(env, ["Ative o modo apresentação", "Quem é você?", "sair"]), 0)
            self.assertIn("Plano da sala indisponível", env.stdout.getvalue())
            self.assertNotIn("token-private", env.stdout.getvalue())
            self.assertEqual(env.http.calls, [])

    def test_sensor_nao_recebe_atuacao(self):
        reply = respond_to_room_operator("Ligue o sensor de presença")
        self.assertEqual(reply.channel, "blocked")
        self.assertFalse(reply.action_verified)
