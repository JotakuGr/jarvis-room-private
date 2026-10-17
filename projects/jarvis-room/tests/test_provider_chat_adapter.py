"""Testes offline da integração entre CLI e registro.

Nenhum modelo real é inicializado.
"""

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis_room.experimental_chat import answer_informational_question
from jarvis_room.inference_policy import InferenceDecision, LocalInferenceUnavailable
from jarvis_room.provider_chat_adapter import LOCAL_PROVIDER_ID, RegistryChatAdapter
from jarvis_room.provider_contract import (
    ProviderRequest,
    ProviderResourceUnavailable,
    ProviderUnavailable,
)
from jarvis_room.room_chat_cli import main


class TestProviderChatAdapter(unittest.TestCase):
    def test_provedor_local_explicito(self) -> None:
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as conversation:
            chat = RegistryChatAdapter()
        providers = chat._registry.list_providers()
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].identifier, LOCAL_PROVIDER_ID)
        self.assertEqual(providers[0].location, "local")
        self.assertTrue(providers[0].enabled)
        conversation.assert_not_called()

    def test_texto_encaminhado_pelo_registro(self) -> None:
        chat = RegistryChatAdapter()
        prompt = "Explique MQTT"
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as conversation, patch.object(
            chat._registry, "respond", wraps=chat._registry.respond
        ) as respond:
            conversation.return_value.return_value = "Resposta simulada"
            self.assertEqual(chat(prompt), "Resposta simulada")
        respond.assert_called_once_with(LOCAL_PROVIDER_ID, ProviderRequest(prompt))
        conversation.assert_called_once_with()
        conversation.return_value.assert_called_once_with(prompt)

    def test_bloqueio_de_recursos_sem_importar_sdk(self) -> None:
        for reason in (
            "RAM disponível insuficiente para inferência local.",
            "Swap livre insuficiente para inferência local.",
            "Não foi possível verificar os recursos do sistema.",
        ):
            with self.subTest(reason=reason), patch(
                "jarvis_room.conversation_adapter.check_current_resources",
                return_value=InferenceDecision(False, reason),
            ) as check, patch("builtins.__import__", wraps=__import__) as imports:
                with self.assertRaises(LocalInferenceUnavailable) as error:
                    RegistryChatAdapter()("Explique MQTT")
            check.assert_called_once_with()
            self.assertEqual(str(error.exception), reason)
            self.assertIsInstance(
                error.exception.__cause__, ProviderResourceUnavailable
            )
            self.assertIsInstance(error.exception.__cause__, ProviderUnavailable)
            self.assertFalse(any(
                call.args[0] == "openjarvis" for call in imports.call_args_list
            ))

    def test_erro_generico_nao_se_torna_bloqueio_de_recursos(self) -> None:
        chat = RegistryChatAdapter()
        # O texto menciona memória, mas o tipo não é um bloqueio de recursos.
        failure = ProviderUnavailable("Falha interna: memória indisponível.")
        with patch.object(chat._registry, "respond", side_effect=failure):
            with self.assertRaises(ProviderUnavailable) as error:
                chat("Explique MQTT")
            self.assertIs(error.exception, failure)
            reply = answer_informational_question("Explique MQTT", chat)
        self.assertEqual(reply.channel, "blocked")
        self.assertIn("Não foi possível consultar", reply.text)
        self.assertNotIn("Falha interna", reply.text)
        self.assertNotIn("Inferência local bloqueada", reply.text)
        self.assertFalse(reply.action_verified)

    def test_caminhos_deterministicos_nao_chamam_provedor(self) -> None:
        for flags, message, channel, expected in (
            (["--llm"], "Quem é você?", "conversation", "J.A.R.V.I.S."),
            (["--llm"], "Explique a arquitetura da sala", "conversation", "OpenJarvis"),
            (
                ["--llm"], "Quais são os dois monitores da sala?",
                "conversation", "monitor 1",
            ),
            (
                ["--llm"], "Qual é o estado dos recursos da sala?",
                "conversation", "Implementadas (2)",
            ),
            (["--llm"], "Ligue a luz da sala", "control", "Não executei"),
            (["--llm"], "Explique MQTT", "blocked", "Solicitação ainda não habilitada"),
            (
                ["--llm", "--experimental-chat"], "Ligue a luz da sala",
                "blocked", "apenas perguntas informativas",
            ),
        ):
            with self.subTest(message=message, flags=flags), patch(
                "sys.argv", ["room_chat_cli", *flags, message]
            ), patch(
                "jarvis_room.provider_chat_adapter.ProviderRegistry.respond",
                side_effect=AssertionError("Provedor não deveria ser consultado"),
            ) as respond, redirect_stdout(StringIO()) as stdout:
                main()
            respond.assert_not_called()
            self.assertIn(
                f"[canal={channel}; acao_verificada=false]", stdout.getvalue()
            )
            self.assertIn(expected, stdout.getvalue())

    def test_cli_experimental_com_provedor_simulado(self) -> None:
        with patch("sys.argv", [
            "room_chat_cli", "--llm", "--experimental-chat", "Explique MQTT",
        ]), patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as conversation, redirect_stdout(StringIO()) as stdout:
            conversation.return_value.return_value = "MQTT usa um broker."
            main()
        conversation.assert_called_once_with()
        conversation.return_value.assert_called_once_with("Explique MQTT")
        self.assertIn("[canal=experimental; acao_verificada=false]", stdout.getvalue())
        self.assertIn("[RESPOSTA EXPERIMENTAL — NÃO VERIFICADA]", stdout.getvalue())
        self.assertIn("MQTT usa um broker.", stdout.getvalue())

    def test_cli_preserva_mensagem_de_recursos(self) -> None:
        reason = "RAM disponível insuficiente para inferência local."
        with patch("sys.argv", [
            "room_chat_cli", "--llm", "--experimental-chat", "Explique MQTT",
        ]), patch(
            "jarvis_room.conversation_adapter.check_current_resources",
            return_value=InferenceDecision(False, reason),
        ) as check, redirect_stdout(StringIO()) as stdout:
            main()
        check.assert_called_once_with()
        self.assertIn("[canal=blocked; acao_verificada=false]", stdout.getvalue())
        self.assertIn(f"Inferência local bloqueada: {reason}", stdout.getvalue())

    def test_solicitacao_invalida_nao_chega_ao_registro(self) -> None:
        chat = RegistryChatAdapter()
        with patch.object(chat._registry, "respond") as respond:
            for prompt in (None, "", " \n ", 42, "x" * 4097):
                with self.subTest(prompt=prompt), self.assertRaises(ValueError):
                    chat(prompt)
        respond.assert_not_called()
