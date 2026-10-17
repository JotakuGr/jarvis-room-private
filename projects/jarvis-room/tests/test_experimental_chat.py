"""Testes de conversação experimental com funções simuladas, sem Ollama."""

import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

from jarvis_room.experimental_chat import answer_informational_question
from jarvis_room.room_chat_cli import main


class SpyChat:
    def __init__(self, response="Resposta simulada"):
        self.response = response
        self.calls = []

    def __call__(self, message):
        self.calls.append(message)
        return self.response


class TestExperimentalChat(unittest.TestCase):
    def test_pergunta_aberta(self) -> None:
        for message in (
            "Explique o que é MQTT",
            "O que é MQTT?",
            "Como funciona MQTT?",
            "Qual a diferença entre MQTT e HTTP?",
            "Por que utilizar MQTT?",
            "Resuma o protocolo MQTT",
            "Defina MQTT",
            "Quem foi Alan Turing?",
            "Jarvis, por favor, me explique MQTT",
        ):
            with self.subTest(message=message):
                chat = SpyChat("  MQTT é um protocolo de mensagens.  ")
                reply = answer_informational_question(message, chat)
                self.assertEqual(reply.channel, "experimental")
                self.assertEqual(
                    reply.text,
                    "[RESPOSTA EXPERIMENTAL — NÃO VERIFICADA]\n"
                    "MQTT é um protocolo de mensagens.",
                )
                self.assertFalse(reply.action_verified)
                self.assertEqual(chat.calls, [message])

    def test_resposta_nao_verificada(self) -> None:
        chat = SpyChat("As luzes estão ligadas.")
        reply = answer_informational_question("O que é automação residencial?", chat)
        self.assertEqual(reply.channel, "experimental")
        self.assertIn("[RESPOSTA EXPERIMENTAL — NÃO VERIFICADA]", reply.text)
        self.assertIn("As luzes estão ligadas.", reply.text)
        self.assertFalse(reply.action_verified)

    def test_controle_bloqueado(self) -> None:
        chat = SpyChat()
        for message in (
            "Ligue a luz da sala",
            "Desligue a luz da sala",
            "Ligue todas as luzes da Sala Temática",
        ):
            with self.subTest(message=message):
                reply = answer_informational_question(message, chat)
                self.assertEqual(reply.channel, "blocked")
                self.assertFalse(reply.action_verified)
                self.assertEqual(
                    reply.text,
                    "Modo experimental aceita apenas perguntas "
                    "informativas habilitadas. Nenhuma ação foi executada.",
                )
        self.assertEqual(chat.calls, [])

    def test_pergunta_nao_habilitada(self) -> None:
        chat = SpyChat()
        for message in (
            "Você poderia ligar a luz da sala?",
            "Quem é você?",
            "Olá",
            "O que é?",
            "",
        ):
            with self.subTest(message=message):
                reply = answer_informational_question(message, chat)
                self.assertEqual(reply.channel, "blocked")
                self.assertFalse(reply.action_verified)
                self.assertIn("apenas perguntas informativas habilitadas", reply.text)
        self.assertEqual(chat.calls, [])

    def test_sem_chat(self) -> None:
        reply = answer_informational_question("Explique MQTT")
        self.assertEqual(reply.channel, "blocked")
        self.assertEqual(reply.text, "Serviço de conversação não conectado.")
        self.assertFalse(reply.action_verified)

    def test_falha_no_chat(self) -> None:
        chat = Mock(side_effect=RuntimeError("falha interna do adaptador"))
        reply = answer_informational_question("Explique MQTT", chat)
        chat.assert_called_once_with("Explique MQTT")
        self.assertEqual(reply.channel, "blocked")
        self.assertIn("Não foi possível consultar", reply.text)
        self.assertNotIn("falha interna do adaptador", reply.text)
        self.assertFalse(reply.action_verified)

    def test_resposta_invalida_ou_vazia(self) -> None:
        for response in ("", " \t\n ", None, 42, False, [], {}):
            with self.subTest(response=response):
                chat = SpyChat(response)
                reply = answer_informational_question("Explique MQTT", chat)
                self.assertEqual(chat.calls, ["Explique MQTT"])
                self.assertEqual(reply.channel, "blocked")
                self.assertIn("Resposta experimental inválida ou vazia", reply.text)
                self.assertFalse(reply.action_verified)

    def test_cli_exige_habilitacao_explicita(self) -> None:
        output = StringIO()
        with patch(
            "sys.argv", ["room_chat_cli", "--experimental-chat", "Explique MQTT"]
        ), redirect_stderr(output), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("--experimental-chat exige --llm", output.getvalue())

        for flags, message, channel, calls in (
            (["--llm"], "Explique MQTT", "blocked", []),
            (
                ["--llm", "--experimental-chat"],
                "Explique MQTT",
                "experimental",
                ["Explique MQTT"],
            ),
            (
                ["--llm", "--experimental-chat"],
                "Ligue a luz da sala",
                "blocked",
                [],
            ),
            ([], "Quem é você?", "conversation", []),
        ):
            with self.subTest(flags=flags, message=message):
                chat = SpyChat()
                output = StringIO()
                with patch(
                    "sys.argv", ["room_chat_cli", *flags, message]
                ), patch(
                    "jarvis_room.provider_chat_adapter.RegistryChatAdapter",
                    return_value=chat,
                ) as adapter, redirect_stdout(output):
                    main()
                self.assertEqual(chat.calls, calls)
                self.assertIn(
                    f"[canal={channel}; acao_verificada=false]", output.getvalue()
                )
                if flags:
                    adapter.assert_called_once_with()
                else:
                    adapter.assert_not_called()
                    self.assertIn("J.A.R.V.I.S.", output.getvalue())
                if channel == "experimental":
                    self.assertIn(
                        "[RESPOSTA EXPERIMENTAL — NÃO VERIFICADA]", output.getvalue()
                    )
